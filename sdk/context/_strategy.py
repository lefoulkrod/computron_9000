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
from conversations import SummaryRecord, save_summary_record
from sdk.events import get_current_agent_name
from sdk.loop import get_conversation_id

from ._history import ConversationHistory
from ._models import ContextStats

logger = logging.getLogger(__name__)
_console = Console(stderr=True)

# Maximum chars per tool result in the serialized summarization input.
# Tool results are aggressively capped because the assistant messages
# already contain the distilled findings. In typical conversations,
# tool outputs (page snapshots, bash output) are 96% of input chars
# but carry little unique signal beyond what the assistant summarized.
_TOOL_RESULT_CAP = 200


# When serialized conversation exceeds this threshold, switch to chunked
# summarization (split → summarize each chunk → merge).
_CHUNK_THRESHOLD = 20_000

# Target size per chunk in characters. Each chunk gets its own summarizer
# call, so this controls the input size per call.
_CHUNK_TARGET_SIZE = 10_000

# Maximum time (seconds) for a single summarizer LLM call. If the model
# takes longer (e.g. runaway generation, contention), the call is cancelled
# and compaction is skipped rather than blocking the agent indefinitely.
_CALL_TIMEOUT = 120

_SUMMARIZE_PROMPT = (
    "You are a summarizer. Condense the following conversation into a factual "
    "reference document that the assistant can use to continue working.\n"
    "\n"
    "You MUST use EXACTLY this structure with these exact headings. Do not use "
    "any other format. Do not write prose or commentary. Start your response "
    "with '## Completed Work'.\n"
    "\n"
    "## Completed Work\n"
    "List every fact, finding, and result produced so far as bullet points.\n"
    "Focus on RESULTS and FINDINGS, not the steps taken to get them.\n"
    "\n"
    "## Key Data\n"
    "List all specific reference data the user needs to act on the results:\n"
    "URLs/links, prices, ratings, dates, addresses, phone numbers, file paths,\n"
    "code snippets, error messages, version numbers, etc.\n"
    "Format as a structured list. If no key data was gathered, write \"None\".\n"
    "\n"
    "## Current State\n"
    "Describe the current state of the task so the assistant can pick up exactly\n"
    "where it left off: which application or page is open, what files have been\n"
    "modified, which form fields are filled vs pending, what errors are unresolved,\n"
    "cell/row references, coordinates, or other positional details needed to act.\n"
    "If not applicable, write \"None\".\n"
    "\n"
    "## Remaining Work\n"
    "List what still needs to be done, or write \"None\" if the task is complete.\n"
    "\n"
    "RULES:\n"
    "- Your output MUST start with '## Completed Work' and contain all four "
    "sections above. No other format is acceptable.\n"
    "- Preserve FACTS and DATA, not process. Omit HOW results were obtained "
    "(clicks, navigation, scrolling, filter adjustments, retries, error recovery). "
    "Do not describe tool calls, UI interactions, or troubleshooting steps.\n"
    "  WRONG: 'Navigated to Google Flights, set origin to AUS, applied nonstop "
    "filter, clicked search'\n"
    "  RIGHT: 'Searched Google Flights for nonstop AUS→ORD Apr 10-12. Best "
    "options: American $634, United $714, Delta $558'\n"
    "- MUST INCLUDE URLs needed to revisit results or continue work (product pages, "
    "booking pages, data sources, file paths). Omit intermediate navigation URLs "
    "(search engines, category listings, filter pages).\n"
    "- MUST INCLUDE all prices, ratings, quantities, dates, and numerical data "
    "found. These are the primary value of the research.\n"
    "- If the input contains a prior summary, merge ALL its facts into yours — "
    "every URL, price, name, date, and detail from the prior summary MUST appear "
    "in your output. Do not summarize the summary; expand it with new facts.\n"
    "- Never drop specific details (numbers, names, URLs, paths, code) in favor of "
    "vague descriptions like 'highly-rated' or 'well-known'.\n"
    "- Be concise but exhaustive in facts.\n"
    "- Do NOT echo these instructions — replace them with actual content."
)

_SUMMARY_PREFIX = "[Conversation summary — earlier messages were compacted]\n\n"


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


class SummarizeStrategy:
    """Summarizes old conversation history when context fills up.

    When the context fill ratio exceeds *threshold*, sends the oldest
    messages to an LLM for summarization and replaces them with a compact
    summary. The most recent *keep_recent* messages are preserved verbatim.

    Args:
        threshold: Fill ratio above which the strategy activates (0.0–1.0).
        keep_recent: Number of recent non-system messages to preserve verbatim.
        summary_model: Model identifier string override.
            Falls back to the ``summary`` section in config.
    """

    def __init__(
        self,
        threshold: float = 0.75,
        keep_recent: int = 6,
        summary_model: str | None = None,
    ) -> None:
        self._threshold = threshold
        self._keep_recent = keep_recent
        self._summary_model = summary_model

    @property
    def trigger(self) -> TriggerPoint:
        return TriggerPoint.BEFORE_MODEL_CALL

    def should_apply(self, history: ConversationHistory, stats: ContextStats) -> bool:
        return stats.fill_ratio >= self._threshold

    async def apply(self, history: ConversationHistory, stats: ContextStats) -> None:
        """Summarize old messages and replace them with a compact summary."""
        non_system = history.non_system_messages
        if len(non_system) <= self._keep_recent:
            return

        # Pin the first user message — it contains the original request and
        # must never be summarized away.
        first_user_idx, has_pinned = _find_first_user(non_system)
        pin_offset = 1 if has_pinned else 0

        compactable = non_system[pin_offset : -self._keep_recent]
        if not compactable:
            return

        # Extract any prior summary so we can merge facts forward.
        prior_summary = _extract_prior_summary(compactable)

        try:
            summary, model_name = await self._summarize(
                compactable, prior_summary,
            )
        except TimeoutError:
            logger.warning(
                "SummarizeStrategy: compaction timed out after %ds, skipping",
                _CALL_TIMEOUT,
            )
            return
        except Exception:
            logger.exception("SummarizeStrategy: LLM call failed, skipping compaction")
            return

        # Persist the summarization event for quality evaluation.
        cfg = load_config()
        _, resolved_options = self._resolve_model(cfg)
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
            conversation_id=get_conversation_id() or "",
            agent_name=get_current_agent_name() or "",
            options=resolved_options if isinstance(resolved_options, dict) else {},
        )
        save_summary_record(record)

        # Determine the range to drop within the full history list.
        # Skip system message (if any) and the pinned first user message.
        start = (1 if history.system_message is not None else 0) + pin_offset
        end = start + len(compactable)

        _log_summary(stats, len(compactable), summary)

        # Replace compactable messages with summary.
        history.drop_range(start, end)
        history.insert(start, {
            "role": "assistant",
            "content": _SUMMARY_PREFIX + summary,
        })

    async def _summarize(
        self,
        messages: list[dict],
        prior_summary: str | None = None,
    ) -> tuple[str, str]:
        """Summarize messages, chunking if necessary.

        For short conversations, serializes and summarizes in a single call.
        For long conversations, splits into chunks, summarizes each, then
        merges the chunk summaries.
        """
        import copy

        # Serialize to check total size.
        serialized = _serialize_messages(copy.deepcopy(messages))
        if len(serialized) <= _CHUNK_THRESHOLD:
            return await self._call_summarizer(serialized, prior_summary)

        # Split messages into chunks and summarize each independently.
        chunks = _split_into_chunks(messages)
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
            summary, model_name = await self._call_summarizer(chunk_text, ps)
            chunk_summaries.append(summary)

        # Merge chunk summaries in a final pass.
        merged_input = "\n\n---\n\n".join(
            f"[Summary of part {i + 1}/{len(chunk_summaries)}]\n{s}"
            for i, s in enumerate(chunk_summaries)
        )
        final_summary, model_name = await self._call_summarizer(
            merged_input, prior_summary=None,
        )
        return final_summary, model_name

    async def _call_summarizer(
        self, conversation_text: str, prior_summary: str | None = None,
    ) -> tuple[str, str]:
        """Call the summarization LLM and return (summary_text, model_name)."""
        cfg = load_config()
        provider = get_provider()

        model, options = self._resolve_model(cfg)

        user_content = ""
        if prior_summary:
            user_content += (
                "EXISTING SUMMARY (from a previous compaction — merge all these "
                "facts into your output, do not drop any):\n\n"
                + prior_summary
                + "\n\n---\n\nNEW CONVERSATION to merge:\n\n"
            )
        user_content += conversation_text

        response = await asyncio.wait_for(
            provider.chat(
                model=model,
                messages=[
                    {"role": "system", "content": _SUMMARIZE_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                think=False,
                options=options,
            ),
            timeout=_CALL_TIMEOUT,
        )
        return response.message.content or "", model

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


def _log_summary(
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


def _split_into_chunks(messages: list[dict]) -> list[list[dict]]:
    """Split messages into chunks that each fit within ``_CHUNK_TARGET_SIZE``.

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
        if current_size + msg_size > _CHUNK_TARGET_SIZE and current_chunk:
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
    truncated with head+tail.
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
            if tool_calls:
                tool_names = []
                for tc in tool_calls:
                    fn = getattr(tc, "function", None) or tc.get("function", {})
                    name = getattr(fn, "name", None) or fn.get("name", "unknown")
                    tool_names.append(name)
                tools_str = ", ".join(tool_names)
                if content:
                    entries.append(f"Assistant: {content}\n  [Called tools: {tools_str}]")
                else:
                    entries.append(f"Assistant: [Called tools: {tools_str}]")
            elif content:
                entries.append(f"Assistant: {content}")

        elif role == "tool":
            tool_name = msg.get("tool_name", "unknown")
            if len(content) > _TOOL_RESULT_CAP:
                content = content[:_TOOL_RESULT_CAP] + "..."
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


