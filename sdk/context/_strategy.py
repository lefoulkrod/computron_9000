"""Pluggable context management strategies."""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from rich.console import Console

from sdk.providers import get_provider
from rich.panel import Panel
from rich.text import Text

from config import load_config
from conversations import ClearedItem, ClearingRecord, SummaryRecord, save_clearing_record, save_summary_record
from sdk.events import get_current_agent_name
from sdk.turn import get_conversation_id

from ._history import ConversationHistory
from ._models import ContextStats

logger = logging.getLogger(__name__)
_console = Console(stderr=True)

# Default cap on tool result chars in serialized summarization input.
# Overridden per tool type below — code tools need more content since
# the assistant messages are often empty and all signal is in the result.
_TOOL_RESULT_CAP = 200

# Per-tool-type result caps.
# Code tools: the file/grep/bash output IS the data — assistant messages
#   are typically empty (content=0) so the tool result is the only signal.
# Browser tools: page snapshots are large but mostly navigation noise;
#   the assistant already synthesizes findings in its content. A moderate
#   cap captures structured data (prices, ratings) without including menus.
# Default (unknown tools): conservative 200 chars.
_TOOL_RESULT_CAPS: dict[str, int] = {
    # Code — higher cap than default. Agent messages typically already synthesize
    # file contents, so the tool result is supplementary context. 1500 chars
    # captures the module docstring, imports, and first class definition.
    "read_file": 1500,
    "grep": 1500,
    "run_bash_cmd": 1500,
    "list_dir": 800,
    "apply_text_patch": 400,
    "replace_in_file": 400,
    "write_file": 300,
    # Browser — moderate cap, assistant synthesizes page content
    "open_url": 500,
    "read_page": 800,
    "browse_page": 500,
    "scroll_page": 400,
    "click": 200,
    "fill_field": 200,
}

# Maximum chars of the ``thinking`` field to include when the assistant
# message has no visible content.  In coding conversations the assistant
# often makes tool calls with empty content — all analysis lives in
# ``thinking``.  Including an excerpt gives the summarizer context about
# *why* a tool was called (e.g. "reading file to find pause button").
_THINKING_CAP = 200


# Approximate characters per token for estimating chunk boundaries.
_CHARS_PER_TOKEN = 4

# Fraction of the summarizer's context window to use for input.
# Leaves room for the system prompt (~500 tokens) and generated output
# (num_predict, typically 2048 tokens).
_CTX_INPUT_FRACTION = 0.6

# Maximum time (seconds) for a single summarizer LLM call. If the model
# takes longer (e.g. runaway generation, contention), the call is cancelled
# and compaction is skipped rather than blocking the agent indefinitely.
_CALL_TIMEOUT = 180


_SUMMARIZE_PROMPT = (
    "You are a summarizer. Condense the following conversation into a factual "
    "reference document that the assistant can use to continue working. The "
    "conversation may be browser research, code analysis, or both.\n"
    "\n"
    "{objective_line}"
    "You MUST use EXACTLY this structure with these exact headings. Do not use "
    "any other format. Do not write prose or commentary. Start your response "
    "with '## Completed Work'.\n"
    "\n"
    "## Completed Work\n"
    "List every fact, finding, and result produced so far as bullet points.\n"
    "Focus on RESULTS and FINDINGS, not the steps taken to get them.\n"
    "For code tasks: document what key files CONTAIN (APIs, class definitions, "
    "critical logic, function signatures), not just that files were read.\n"
    "For research tasks: document what was found at each source.\n"
    "\n"
    "## Key Data\n"
    "List all specific reference data needed to continue the work:\n"
    "- Research: URLs/links, prices, ratings, dates, addresses, phone numbers, "
    "version numbers\n"
    "- Code: file paths, function/method signatures, class definitions, API "
    "contracts, import paths, error messages, test results, shell command output\n"
    "Format as a structured list grouped by type. If no key data was gathered, "
    "write \"None\".\n"
    "\n"
    "## Current State\n"
    "Describe what is happening RIGHT NOW at the end of the conversation.\n"
    "What was the assistant doing? What does it still need to do to complete "
    "the objective? Include any in-progress work, unresolved errors, or "
    "pending actions. If not applicable, write \"None\".\n"
    "\n"
    "RULES:\n"
    "- Your output MUST start with '## Completed Work' and contain all three "
    "sections above. No other format is acceptable.\n"
    "- Preserve FACTS and DATA, not process. Drop operational details "
    "(navigation steps, scroll positions, viewport positions, failed commands, "
    "file line numbers) unless they indicate an active blocker.\n"
    "  Browser WRONG: 'Navigated to Google Flights, applied nonstop filter, "
    "clicked search'\n"
    "  Browser RIGHT: 'Searched Google Flights nonstop AUS→ORD Apr 10-12. "
    "Best: American $634, United $714, Delta $558'\n"
    "  Code WRONG: 'Read sdk/events/_dispatcher.py'\n"
    "  Code RIGHT: 'EventDispatcher (sdk/events/_dispatcher.py): async pub/sub, "
    "subscribe(handler)/unsubscribe()/publish(event) methods, supports async "
    "context manager'\n"
    "- For code: preserve key signatures, field names, and behavioural details "
    "found in file contents — these are the primary value of code analysis.\n"
    "- For research: MUST INCLUDE URLs needed to revisit results. Omit "
    "intermediate navigation URLs (search engines, category listings).\n"
    "- MUST INCLUDE all prices, ratings, quantities, dates, and numerical data.\n"
    "- If the input contains a prior summary, RE-CONDENSE it together with the "
    "new information into a single tight summary. Integrate and deduplicate — "
    "do NOT copy the prior summary verbatim. The output should be shorter or "
    "the same length unless significant new facts were added.\n"
    "- Never drop specific details (numbers, names, URLs, paths, signatures) in "
    "favor of vague descriptions like 'highly-rated' or 'well-known'.\n"
    "- Be concise but exhaustive in facts.\n"
    "- Do NOT echo these instructions — replace them with actual content."
)


def _build_summarize_prompt(objective: str = "") -> str:
    """Build the summarizer system prompt, optionally injecting the objective."""
    if objective:
        objective_line = (
            f'THE AGENT\'S OBJECTIVE: "{objective}"\n'
            "Prioritize information the agent needs to complete this objective.\n\n"
        )
    else:
        objective_line = ""
    return _SUMMARIZE_PROMPT.format(objective_line=objective_line)


_SUMMARY_PREFIX = "[Conversation summary — earlier messages were compacted]\n\n"

# Prefix for the synthetic user message that replaces the stale pinned
# first user message after intent extraction (experiment 29).
_INTENT_PREFIX = "[User intent history]\n"

# Prompt for extracting the user's current intent from multiple user
# messages.  Only called when the compactable range contains more than
# one user message, indicating the user changed topics or refined their
# request during the conversation.
_INTENT_EXTRACTION_PROMPT = (
    "You will be given a sequence of user messages from a multi-turn "
    "conversation with an AI assistant. The user may have changed topics "
    "or given new instructions over the course of the conversation.\n\n"
    "Write a concise history of the user's inputs that shows how their "
    "requests evolved. Start with the original request and trace through "
    "topic changes, refinements, and redirections to arrive at the current "
    "intent. Use a compact format — one line per phase. Mark the current "
    "active request clearly with [CURRENT] prefix.\n\n"
    "Output ONLY the history. Be concise — each line should be one "
    "sentence max."
)


class TriggerPoint(StrEnum):
    """When a strategy should be evaluated."""

    BEFORE_MODEL_CALL = "before_model_call"
    AFTER_MODEL_CALL = "after_model_call"


class ContextStrategy(Protocol):
    """Interface for context management strategies."""

    @property
    def trigger(self) -> TriggerPoint:
        """When this strategy should be evaluated."""
        ...

    def should_apply(self, history: ConversationHistory, stats: ContextStats) -> bool:
        """Whether this strategy needs to act given the current state."""
        ...

    async def apply(self, history: ConversationHistory, stats: ContextStats) -> None:
        """Mutate *history* to reduce context usage."""
        ...


# Stub that replaces cleared tool result content.
_CLEARED_TOOL_RESULT = "[tool result cleared]"

# Maximum chars for a tool call argument value before it gets truncated
# during clearing. Short values (file paths, commands, URLs) are naturally
# under this limit; only bulk data (file contents, large patches) exceeds it.
_ARG_CLEAR_CAP = 200


class ToolClearingStrategy:
    """Clear old tool results and large tool-call arguments to free context.

    A lightweight, zero-LLM-cost strategy that runs before the expensive
    ``SummarizeStrategy``. By replacing already-processed tool outputs with
    short stubs, it can free 60-90% of context and delay or avoid
    LLM-based summarization entirely.

    Safety rule: only clears tool results that have a subsequent assistant
    message in the clearable range, meaning the assistant already processed
    and summarized the result. Tool results at the tail (not yet processed)
    are left intact.

    Args:
        threshold: Fill ratio above which clearing activates (0.0–1.0).
            Set to 0.0 to disable.
        keep_recent_groups: Number of recent assistant message groups to
            protect from clearing.
    """

    def __init__(
        self,
        threshold: float = 0.0,
        keep_recent_groups: int = 2,
    ) -> None:
        self._threshold = threshold
        self._keep_recent_groups = keep_recent_groups

    @property
    def trigger(self) -> TriggerPoint:
        return TriggerPoint.BEFORE_MODEL_CALL

    def should_apply(self, history: ConversationHistory, stats: ContextStats) -> bool:
        if self._threshold <= 0.0:
            return False
        return stats.fill_ratio >= self._threshold

    async def apply(self, history: ConversationHistory, stats: ContextStats) -> None:
        """Clear old tool results and large args in place."""
        total = len(history)

        # Find first user message (pinned — never touched).
        pin_end = 0
        for i in range(total):
            msg = history.get_mutable(i)
            if msg.get("role") == "system":
                continue
            if msg.get("role") == "user":
                content = msg.get("content") or ""
                if not content.startswith(_SUMMARY_PREFIX):
                    pin_end = i + 1
                    break

        # Build a lightweight role list for boundary calculation.
        body = [history.get_mutable(i) for i in range(pin_end, total)]
        keep_count = _count_kept_by_assistant_groups(
            body, self._keep_recent_groups,
        )
        boundary = pin_end + len(body) - keep_count

        # Pre-scan roles so _has_following_assistant doesn't need the list.
        roles = [history.get_mutable(i).get("role", "") for i in range(total)]

        results_cleared = 0
        args_cleared = 0
        total_chars_freed = 0
        cleared_items: list[ClearedItem] = []

        for i in range(pin_end, boundary):
            msg = history.get_mutable(i)
            role = roles[i]

            if role == "tool":
                content = msg.get("content") or ""
                if (
                    len(content) > len(_CLEARED_TOOL_RESULT)
                    and _has_following_assistant_roles(roles, i, boundary)
                ):
                    chars_freed = len(content) - len(_CLEARED_TOOL_RESULT)
                    cleared_items.append(ClearedItem(
                        message_index=i,
                        role="tool",
                        tool_name=msg.get("tool_name", ""),
                        cleared_type="tool_result",
                        original_content=content,
                        original_chars=len(content),
                    ))
                    msg["content"] = _CLEARED_TOOL_RESULT
                    results_cleared += 1
                    total_chars_freed += chars_freed

            elif role == "assistant":
                if not _has_following_assistant_roles(roles, i, boundary):
                    continue
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function") or tc
                    tool_name = fn.get("name", "")
                    args = fn.get("arguments")
                    if not isinstance(args, dict):
                        continue
                    for key, val in args.items():
                        val_str = str(val)
                        if len(val_str) > _ARG_CLEAR_CAP:
                            truncated = (
                                val_str[:_ARG_CLEAR_CAP]
                                + f"... [{len(val_str):,} chars]"
                            )
                            chars_freed = len(val_str) - len(truncated)
                            cleared_items.append(ClearedItem(
                                message_index=i,
                                role="assistant",
                                tool_name=tool_name,
                                cleared_type="tool_arg",
                                arg_key=key,
                                original_content=val_str,
                                original_chars=len(val_str),
                            ))
                            args[key] = truncated
                            args_cleared += 1
                            total_chars_freed += chars_freed

        if results_cleared or args_cleared:
            logger.info(
                "ToolClearingStrategy: cleared %d tool results, "
                "%d large args, freed %s chars (fill=%.0f%%)",
                results_cleared, args_cleared,
                f"{total_chars_freed:,}", stats.fill_ratio * 100,
            )
            self._save_record(
                history, stats, results_cleared, args_cleared,
                total_chars_freed, cleared_items,
            )

    def _save_record(
        self,
        history: ConversationHistory,
        stats: ContextStats,
        results_cleared: int,
        args_cleared: int,
        total_chars_freed: int,
        cleared_items: list[ClearedItem],
    ) -> None:
        """Persist a ClearingRecord for offline quality evaluation."""
        record = ClearingRecord(
            id=str(uuid.uuid4()),
            created_at=datetime.now(UTC).isoformat(),
            conversation_id=get_conversation_id() or "default",
            agent_name=get_current_agent_name() or "",
            fill_ratio=stats.fill_ratio,
            total_chars_freed=total_chars_freed,
            results_cleared=results_cleared,
            args_cleared=args_cleared,
            threshold=self._threshold,
            keep_recent_groups=self._keep_recent_groups,
            cleared_items=cleared_items,
            source_history=history.instance_id,
        )
        try:
            save_clearing_record(record)
        except Exception:
            logger.exception("Failed to save clearing record")


def _has_following_assistant_roles(
    roles: list[str], start: int, end: int,
) -> bool:
    """Check if an assistant message exists between *start*+1 and *end*."""
    for j in range(start + 1, end):
        if roles[j] == "assistant":
            return True
    return False


class LLMCompactionStrategy:
    """Summarizes old conversation history when context fills up.

    When the context fill ratio exceeds *threshold*, sends the oldest
    messages to an LLM for summarization and replaces them with a compact
    summary. The most recent messages are preserved verbatim, with the
    boundary determined by assistant message groups to avoid splitting
    tool calls from their results.

    Args:
        threshold: Fill ratio above which the strategy activates (0.0–1.0).
        keep_recent_groups: Number of recent assistant message groups to
            preserve. Each group is an assistant message plus its tool
            results. Any user or other messages interleaved between kept
            groups are also preserved.
        summary_model: Model identifier string override.
            Falls back to the ``summary`` section in config.
    """

    def __init__(
        self,
        threshold: float = 0.75,
        keep_recent_groups: int = 2,
        summary_model: str | None = None,
    ) -> None:
        self._threshold = threshold
        self._keep_recent_groups = keep_recent_groups
        self._summary_model = summary_model

    @property
    def trigger(self) -> TriggerPoint:
        return TriggerPoint.BEFORE_MODEL_CALL

    def should_apply(self, history: ConversationHistory, stats: ContextStats) -> bool:
        return stats.fill_ratio >= self._threshold

    async def apply(self, history: ConversationHistory, stats: ContextStats) -> None:
        """Summarize old messages and replace them with a compact summary."""
        non_system = history.non_system_messages

        # Pin the first user message — it will be kept but may be updated
        # with an extracted intent history if the user changed topics.
        first_user_idx, has_pinned = _find_first_user(non_system)
        pin_offset = 1 if has_pinned else 0

        body = non_system[pin_offset:]
        keep_count = _count_kept_by_assistant_groups(
            body, self._keep_recent_groups,
        )
        if keep_count >= len(body):
            return

        compactable = body[:-keep_count] if keep_count > 0 else body
        if not compactable:
            return

        # Collect all user messages before history mutation for intent
        # extraction.  Includes the pinned message, compactable, and kept.
        all_user_contents = []
        for m in non_system:
            if m.get("role") == "user":
                content = m.get("content") or ""
                if content and not content.startswith(_SUMMARY_PREFIX):
                    all_user_contents.append(content)

        # Extract any prior summary so we can merge facts forward.
        prior_summary = _extract_prior_summary(compactable)

        # Resolve model name up front so we can unload on any exit path.
        cfg = load_config()
        resolved_model, resolved_options = self._resolve_model(cfg)

        import time as _time
        t0 = _time.monotonic()
        try:
            summary, model_name = await self._summarize(
                compactable, prior_summary,
            )
        except TimeoutError:
            logger.warning(
                "LLMCompactionStrategy: compaction timed out after %ds, skipping",
                _CALL_TIMEOUT,
            )
            _unload_model(resolved_model)
            return
        except Exception:
            logger.exception("LLMCompactionStrategy: LLM call failed, skipping compaction")
            _unload_model(resolved_model)
            return
        elapsed = _time.monotonic() - t0

        # Extract user intent if multiple user messages exist (experiment 29).
        # When the user changes topics mid-conversation, the pinned first
        # message becomes stale.  Replace it with an LLM-extracted intent
        # history that tracks how the user's requests evolved.
        intent_history = None
        if has_pinned and len(all_user_contents) > 1:
            try:
                intent_history = await self._extract_intent(all_user_contents)
                logger.info(
                    "LLMCompactionStrategy: extracted intent from %d user messages",
                    len(all_user_contents),
                )
            except Exception:
                logger.exception(
                    "Intent extraction failed, keeping original pinned message",
                )

        # Persist the summarization event for quality evaluation.
        record = SummaryRecord(
            id=str(uuid.uuid4()),
            created_at=datetime.now(UTC).isoformat(),
            model=model_name,
            input_messages=compactable,
            input_char_count=sum(len(m.get("content") or "") for m in compactable),
            prior_summary=prior_summary,
            summary_text=summary,
            summary_char_count=len(summary),
            messages_compacted=len(compactable),
            fill_ratio=stats.fill_ratio,
            conversation_id=get_conversation_id() or "default",
            agent_name=get_current_agent_name() or "",
            options=resolved_options if isinstance(resolved_options, dict) else {},
            elapsed_seconds=round(elapsed, 1),
            source_history=history.instance_id,
            user_message_post_compaction=intent_history,
        )

        # Save the pinned user message content before mutation. On the first
        # compaction this is the user's real original message; on subsequent
        # compactions it's the previous intent history. The true original is
        # in the earliest summary record (by created_at).
        if has_pinned:
            pinned_idx = 1 if history.system_message is not None else 0
            record.user_message_pre_compaction = (
                history.get_mutable(pinned_idx).get("content") or ""
            )

        save_summary_record(record)

        # Determine the range to drop within the full history list.
        # Skip system message (if any) and the pinned first user message.
        start = (1 if history.system_message is not None else 0) + pin_offset
        end = start + len(compactable)

        _log_compaction(stats, len(compactable), summary)

        # Replace compactable messages with summary.
        history.drop_range(start, end)
        history.insert(start, {
            "role": "assistant",
            "content": _SUMMARY_PREFIX + summary,
        })

        # Update the pinned first user message with the extracted intent
        # history so the agent sees the current objective, not the stale
        # original request.
        if intent_history is not None and has_pinned:
            pinned_idx = 1 if history.system_message is not None else 0
            pinned_msg = history.get_mutable(pinned_idx)
            pinned_msg["content"] = _INTENT_PREFIX + intent_history

        # Unload the summarizer model to free VRAM for the main agent.
        _unload_model(model_name)

    async def _summarize(
        self,
        messages: list[dict],
        prior_summary: str | None = None,
        objective: str = "",
    ) -> tuple[str, str]:
        """Summarize messages, chunking if necessary.

        For short conversations, serializes and summarizes in a single call.
        For long conversations, splits into chunks, summarizes each, then
        merges the chunk summaries. The chunk threshold scales with the
        summarizer's configured context window.
        """
        import copy

        cfg = load_config()
        _, options = self._resolve_model(cfg)
        num_ctx = options.get("num_ctx", 8192) if isinstance(options, dict) else 8192
        chunk_threshold = int(num_ctx * _CHARS_PER_TOKEN * _CTX_INPUT_FRACTION)
        chunk_target = chunk_threshold // 2

        # Serialize to check total size.
        serialized = _serialize_messages(copy.deepcopy(messages))
        if len(serialized) <= chunk_threshold:
            return await self._call_summarizer(
                serialized, prior_summary, objective,
            )

        # Split messages into chunks and summarize each independently.
        chunks = _split_into_chunks(messages, chunk_target)
        logger.info(
            "Chunked summarization: %d messages → %d chunks",
            len(messages), len(chunks),
        )

        chunk_summaries: list[str] = []
        model_name = ""
        for i, chunk in enumerate(chunks):
            chunk_text = _serialize_messages(copy.deepcopy(chunk))
            # Include prior summary context only in the first chunk.
            ps = prior_summary if i == 0 else None
            summary, model_name = await self._call_summarizer(
                chunk_text, ps, objective,
            )
            chunk_summaries.append(summary)

        # Merge chunk summaries in a final pass.
        merged_input = "\n\n---\n\n".join(
            f"[Summary of part {i + 1}/{len(chunk_summaries)}]\n{s}"
            for i, s in enumerate(chunk_summaries)
        )
        final_summary, model_name = await self._call_summarizer(
            merged_input, prior_summary=None, objective=objective,
        )
        return final_summary, model_name

    async def _call_summarizer(
        self,
        conversation_text: str,
        prior_summary: str | None = None,
        objective: str = "",
    ) -> tuple[str, str]:
        """Call the summarization LLM and return (summary_text, model_name)."""
        cfg = load_config()
        provider = get_provider()

        model, options = self._resolve_model(cfg)

        user_content = ""
        if prior_summary:
            user_content += (
                "PRIOR SUMMARY (from a previous compaction — integrate into "
                "your output, re-condensing where possible):\n\n"
                + prior_summary
                + "\n\n---\n\nNEW MESSAGES since last compaction:\n\n"
            )
        user_content += conversation_text

        system_prompt = _build_summarize_prompt(objective)
        response = await asyncio.wait_for(
            provider.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                think=False,
                options=options,
            ),
            timeout=_CALL_TIMEOUT,
        )
        return response.message.content or "", model

    async def _extract_intent(self, user_messages: list[str]) -> str:
        """Extract the user's current intent from multiple user messages.

        Called during compaction when the conversation has more than one
        user message, indicating the user may have changed topics.  Uses
        the same model as the summarizer.
        """
        cfg = load_config()
        provider = get_provider()
        model, options = self._resolve_model(cfg)

        # Build the user content with numbered messages.
        # Truncate individual messages to keep the input focused.
        user_content = ""
        for i, msg in enumerate(user_messages):
            text = msg[:500] + "..." if len(msg) > 500 else msg
            user_content += f"\n--- Message {i + 1} ---\n{text}\n"

        response = await asyncio.wait_for(
            provider.chat(
                model=model,
                messages=[
                    {"role": "system", "content": _INTENT_EXTRACTION_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                think=False,
                options={
                    **(options if isinstance(options, dict) else {}),
                    "temperature": 0,
                },
            ),
            timeout=60,
        )
        return response.message.content or ""

    def _resolve_model(self, cfg: object) -> tuple[str, dict]:
        """Determine which model and options to use for summarization."""
        # Explicit override
        if self._summary_model:
            return self._summary_model, {}

        # Use the summary section from config
        summary_cfg = getattr(cfg, "summary", None)
        if summary_cfg is None:
            msg = "No summary model configured. Add a 'summary' section to config.yaml."
            raise RuntimeError(msg)
        return summary_cfg.model, summary_cfg.options


_NUDGE_MESSAGE = (
    "[System] Context is filling up and older messages will be compacted. "
    "Before that happens, emit a detailed summary of your key findings so "
    "far — what you've learned, data gathered, architecture patterns, "
    "important details. This is NOT a request to stop — after summarizing, "
    "continue working on your task as normal."
)

# Marker prefix so the strategy can identify its own nudge in history.
_NUDGE_PREFIX = "[System] Context is filling up"


class NudgeCompactionStrategy:
    """Compacts context by asking the agent to self-summarize.

    Two-phase approach that leverages the agent's own model (already loaded,
    full context available) instead of an external summarizer:

    Phase 1 (nudge): When fill ratio exceeds *threshold*, injects a user
    message asking the agent to summarize its findings. Returns immediately
    so the normal turn loop sends the nudge to the model.

    Phase 2 (compact): On the next trigger, the agent's synthesis response
    is in history. Replaces old messages (up to and including the nudge)
    with the agent's response as the compaction summary.

    Args:
        threshold: Fill ratio above which compaction activates (0.0–1.0).
        keep_recent_groups: Number of recent assistant message groups to
            preserve from compaction.
    """

    def __init__(
        self,
        threshold: float = 0.75,
        keep_recent_groups: int = 2,
    ) -> None:
        self._threshold = threshold
        self._keep_recent_groups = keep_recent_groups
        self._nudge_pending = False

    @property
    def trigger(self) -> TriggerPoint:
        return TriggerPoint.BEFORE_MODEL_CALL

    def should_apply(self, history: ConversationHistory, stats: ContextStats) -> bool:
        if self._nudge_pending:
            # Always run phase 2 if a nudge is waiting to be compacted.
            return True
        if self._threshold <= 0.0:
            return False
        return stats.fill_ratio >= self._threshold

    async def apply(self, history: ConversationHistory, stats: ContextStats) -> None:
        """Inject nudge or compact based on current phase."""
        if not self._nudge_pending:
            # Phase 1: inject nudge, let the model respond on the next iteration.
            self._nudge_pending = True
            history.append({"role": "user", "content": _NUDGE_MESSAGE})
            logger.info(
                "NudgeCompactionStrategy: nudge injected (fill=%.0f%%)",
                stats.fill_ratio * 100,
            )
            return

        # Phase 2: the model has responded to the nudge. Find the synthesis
        # and use it as the compaction summary.
        self._nudge_pending = False

        non_system = history.non_system_messages
        first_user_idx, has_pinned = _find_first_user(non_system)
        pin_offset = 1 if has_pinned else 0

        body = non_system[pin_offset:]
        keep_count = _count_kept_by_assistant_groups(
            body, self._keep_recent_groups,
        )
        if keep_count >= len(body):
            return

        compactable = body[:-keep_count] if keep_count > 0 else body
        if not compactable:
            return

        # Find the agent's synthesis — the last assistant message in the
        # compactable range (should be the response to our nudge).
        synthesis = ""
        for msg in reversed(compactable):
            if msg.get("role") == "assistant" and msg.get("content"):
                synthesis = msg["content"]
                break

        if not synthesis:
            logger.warning("NudgeCompactionStrategy: no synthesis found, skipping")
            return

        # Determine the range to drop within the full history list.
        start = (1 if history.system_message is not None else 0) + pin_offset
        end = start + len(compactable)

        _log_compaction(stats, len(compactable), synthesis)

        # Replace compacted messages with the agent's own synthesis.
        history.drop_range(start, end)
        history.insert(start, {
            "role": "assistant",
            "content": _SUMMARY_PREFIX + synthesis,
        })

        # Persist the compaction event for quality evaluation.
        record = SummaryRecord(
            id=str(uuid.uuid4()),
            created_at=datetime.now(UTC).isoformat(),
            model="nudge",
            input_messages=compactable,
            input_char_count=sum(len(m.get("content") or "") for m in compactable),
            prior_summary=_extract_prior_summary(compactable),
            summary_text=synthesis,
            summary_char_count=len(synthesis),
            messages_compacted=len(compactable),
            fill_ratio=stats.fill_ratio,
            conversation_id=get_conversation_id() or "default",
            agent_name=get_current_agent_name() or "",
        )
        save_summary_record(record)


def _unload_model(model: str) -> None:
    """Unload a model from Ollama to free VRAM."""
    import subprocess
    try:
        subprocess.run(
            ["ollama", "stop", model],
            capture_output=True, timeout=30,
        )
    except Exception:
        logger.debug("Failed to unload model %s", model)


def _log_compaction(
    stats: ContextStats,
    msg_count: int,
    summary: str,
) -> None:
    """Render a Rich panel showing the context summarization result."""
    header = Text()
    header.append(f"Compacted {msg_count} messages", style="bold")
    header.append(f"  fill={stats.fill_ratio:.0%}", style="yellow")
    header.append(f"  → {len(summary):,} chars", style="green")

    _console.print(Panel(
        Text(summary),
        title="[bold magenta]Context Summary[/bold magenta]",
        subtitle=header,
        border_style="magenta",
        expand=False,
    ))


def _count_kept_by_assistant_groups(
    messages: list[dict],
    keep_groups: int,
) -> int:
    """Count how many messages from the tail to keep based on assistant groups.

    Walks backward through *messages* counting assistant messages (with or
    without tool calls). When *keep_groups* assistant messages have been
    found, the boundary is set right before the earliest one found. Any
    non-assistant messages (user messages, tool results) that fall between
    or after the kept assistant messages are included automatically.

    Returns the number of raw messages to keep from the end.
    """
    if keep_groups <= 0 or not messages:
        return 0

    assistant_count = 0
    boundary = len(messages)

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.get("role") == "assistant":
            assistant_count += 1
            boundary = i
            if assistant_count >= keep_groups:
                break

    if assistant_count == 0:
        return 0

    return len(messages) - boundary


# Keys from tool call arguments worth including in the serialized summary.
# Maps tool name → list of argument keys to extract. Keys are checked in
# order; the first present key is used. Values over 200 chars are truncated.
_TOOL_ARG_KEYS: dict[str, list[str]] = {
    "write_file": ["path"],
    "read_file": ["path"],
    "apply_text_patch": ["path"],
    "replace_in_file": ["path"],
    "run_bash_cmd": ["cmd", "command"],
    "open_url": ["url"],
    "click": ["selector", "ref"],
    "fill_field": ["selector", "ref"],
    "grep": ["pattern", "query"],
    "list_dir": ["path"],
    "generate_image": ["prompt"],
    "describe_image": ["path", "image_path"],
}


def _summarize_tool_args(tool_name: str, fn: object) -> str:
    """Extract a short summary of tool call arguments for serialization."""
    keys = _TOOL_ARG_KEYS.get(tool_name)
    if not keys:
        return ""

    raw_args = getattr(fn, "arguments", None) or fn.get("arguments", {})  # type: ignore[union-attr]
    if isinstance(raw_args, str):
        try:
            import json as _json
            raw_args = _json.loads(raw_args)
        except (ValueError, TypeError):
            return ""
    if not isinstance(raw_args, dict):
        return ""

    parts = []
    for key in keys:
        val = raw_args.get(key)
        if val is not None:
            val_str = str(val)
            if len(val_str) > 200:
                val_str = val_str[:200] + "..."
            parts.append(val_str)

    return ", ".join(parts)


# Patterns that indicate a tool result carries no useful information.
_TRIVIAL_PATTERNS = [
    "{'success': True",
    '{"success": true',
    "{'stdout': None, 'stderr': None, 'exit_code': 0}",
    "{'stdout': '', 'stderr': None, 'exit_code': 0}",
    "{'stdout': '', 'stderr': '', 'exit_code': 0}",
    "{'stdout': None, 'stderr': '', 'exit_code': 0}",
]


def _is_trivial_tool_result(content: str) -> bool:
    """Check if a tool result is trivially empty and can be skipped."""
    stripped = content.strip()
    if not stripped:
        return True
    for pattern in _TRIVIAL_PATTERNS:
        if stripped.startswith(pattern) and len(stripped) < 200:
            return True
    return False


def _find_first_user(non_system: list[dict]) -> tuple[int, bool]:
    """Return the index of the first user message and whether one was found."""
    for i, msg in enumerate(non_system):
        if msg.get("role") == "user":
            content = msg.get("content") or ""
            # New summaries use "assistant" role and are skipped naturally.
            # The prefix check is legacy safety for old conversations where
            # summaries had "user" role.
            if not content.startswith(_SUMMARY_PREFIX):
                return i, True
    return 0, False


def _extract_prior_summary(messages: list[dict]) -> str | None:
    """Find and return the most recent prior summary from old messages."""
    for msg in messages:
        content = msg.get("content") or ""
        if content.startswith(_SUMMARY_PREFIX):
            return content[len(_SUMMARY_PREFIX):]
    return None


def _split_into_chunks(
    messages: list[dict],
    target_size: int = 10_000,
) -> list[list[dict]]:
    """Split messages into chunks of approximately *target_size* characters.

    Keeps assistant + tool-call pairs together so a tool call and its
    result are never separated across chunks.
    """
    chunks: list[list[dict]] = []
    current_chunk: list[dict] = []
    current_size = 0

    for msg in messages:
        content = msg.get("content") or ""
        msg_size = len(content)

        # If adding this message would exceed the target and the chunk
        # already has content, start a new chunk.
        if current_size + msg_size > target_size and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0

        current_chunk.append(msg)
        current_size += msg_size

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _serialize_messages(messages: list[dict]) -> str:
    """Serialize a list of messages into readable text for summarization.

    Browser tool results that return page snapshots are deduplicated — only
    the last snapshot per URL is kept in full, earlier ones are replaced with
    a short note. Individual tool results over ``_TOOL_RESULT_CAP`` are
    truncated.
    """
    _dedup_page_snapshots(messages)

    entries: list[str] = []

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content") or ""

        # Summary messages are handled separately via _extract_prior_summary().
        # Skip regardless of role to avoid double-inclusion (new summaries use
        # "assistant" role, legacy ones may still have "user").
        if content.startswith(_SUMMARY_PREFIX):
            continue

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            # Include a truncated thinking excerpt — it often contains
            # synthesized findings and reasoning that the visible content
            # lacks (e.g. "found the Agent class has 8 fields...").
            thinking = ""
            raw_thinking = msg.get("thinking") or ""
            if raw_thinking:
                thinking = raw_thinking[:_THINKING_CAP]
                if len(raw_thinking) > _THINKING_CAP:
                    thinking += "..."

            if tool_calls:
                tool_parts = []
                for tc in tool_calls:
                    fn = getattr(tc, "function", None) or tc.get("function", {})
                    name = getattr(fn, "name", None) or fn.get("name", "unknown")
                    args_summary = _summarize_tool_args(name, fn)
                    if args_summary:
                        tool_parts.append(f"{name}({args_summary})")
                    else:
                        tool_parts.append(name)
                tools_str = ", ".join(tool_parts)
                if content and thinking:
                    entries.append(
                        f"Assistant: {content}\n  (thinking: {thinking})\n  [Called: {tools_str}]",
                    )
                elif content:
                    entries.append(f"Assistant: {content}\n  [Called: {tools_str}]")
                elif thinking:
                    entries.append(
                        f"Assistant (thinking: {thinking})\n  [Called: {tools_str}]",
                    )
                else:
                    entries.append(f"Assistant: [Called: {tools_str}]")
            elif content and thinking:
                entries.append(f"Assistant: {content}\n  (thinking: {thinking})")
            elif content:
                entries.append(f"Assistant: {content}")
            elif thinking:
                entries.append(f"Assistant (thinking: {thinking})")

        elif role == "tool":
            tool_name = msg.get("tool_name", "unknown")
            if _is_trivial_tool_result(content):
                continue
            cap = _TOOL_RESULT_CAPS.get(tool_name, _TOOL_RESULT_CAP)
            if len(content) > cap:
                content = content[:cap] + "..."
            entries.append(f"Tool ({tool_name}): {content}")

        elif role == "user":
            entries.append(f"User: {content}")

    return "\n\n".join(entries)


def _dedup_page_snapshots(messages: list[dict]) -> None:
    """Replace earlier page snapshots for the same URL with a short note.

    Mutates *messages* in place. Only the last tool result containing a
    given base URL is kept in full; earlier duplicates are collapsed to
    ``[page snapshot — superseded by later snapshot]``.
    """
    import re

    # Build a map of base_url → index of last message with that URL.
    _PAGE_PREFIX_RE = re.compile(r"^\[Page: .+? \| (https?://[^\s|]+)")
    last_seen: dict[str, int] = {}
    for i, msg in enumerate(messages):
        if msg.get("role") != "tool":
            continue
        content = msg.get("content") or ""
        m = _PAGE_PREFIX_RE.match(content)
        if m:
            # Strip query params for dedup — same page, different scroll/state.
            base_url = m.group(1).split("?")[0]
            last_seen[base_url] = i

    # Replace earlier duplicates.
    for i, msg in enumerate(messages):
        if msg.get("role") != "tool":
            continue
        content = msg.get("content") or ""
        m = _PAGE_PREFIX_RE.match(content)
        if m:
            base_url = m.group(1).split("?")[0]
            if last_seen.get(base_url) != i:
                msg["content"] = "[page snapshot — superseded by later snapshot]"


