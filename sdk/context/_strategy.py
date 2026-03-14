"""Pluggable context management strategies."""

import json
import logging
from enum import StrEnum
from typing import Protocol

from rich.console import Console

from sdk.providers import get_provider
from rich.panel import Panel
from rich.text import Text

from config import load_config

from ._history import ConversationHistory
from ._models import ContextStats

logger = logging.getLogger(__name__)
_console = Console(stderr=True)

_SUMMARIZE_PROMPT = (
    "Condense the following conversation into a factual reference document that "
    "the assistant can use to continue working.\n"
    "\n"
    "Use EXACTLY this structure (replace the instructions with actual content):\n"
    "\n"
    "## User's Request\n"
    "State the user's full original request in one or two sentences.\n"
    "\n"
    "## Completed Work\n"
    "List every fact, finding, and result produced so far as bullet points.\n"
    "Include: specific data (names, dates, numbers), URLs visited, file paths "
    "created/modified, key content retrieved.\n"
    "\n"
    "## Remaining Work\n"
    "List what still needs to be done, or write \"None\" if the task is complete.\n"
    "\n"
    "RULES:\n"
    "- Preserve FACTS, not process. Write 'Python was created by Guido van Rossum "
    "in 1991', NOT 'The assistant looked up information about Python'.\n"
    "- If the input contains a prior summary, merge all its facts into yours — "
    "do not summarize the summary, expand it with new facts from the conversation.\n"
    "- Never drop specific details (numbers, names, URLs, paths, code) in favor of "
    "vague descriptions.\n"
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

        # Serialize compactable messages for the summarization prompt.
        conversation_text = _serialize_messages(compactable)

        try:
            summary = await self._call_summarizer(conversation_text, prior_summary)
        except Exception:
            logger.exception("SummarizeStrategy: LLM call failed, skipping compaction")
            return

        # Determine the range to drop within the full history list.
        # Skip system message (if any) and the pinned first user message.
        start = (1 if history.system_message is not None else 0) + pin_offset
        end = start + len(compactable)

        _log_summary(stats, len(compactable), summary)

        # Replace compactable messages with summary.
        history.drop_range(start, end)
        history.insert(start, {
            "role": "user",
            "content": _SUMMARY_PREFIX + summary,
        })

    async def _call_summarizer(
        self, conversation_text: str, prior_summary: str | None = None,
    ) -> str:
        """Call the summarization LLM and return the summary text."""
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

        response = await provider.chat(
            model=model,
            messages=[
                {"role": "system", "content": _SUMMARIZE_PROMPT},
                {"role": "user", "content": user_content},
            ],
            think=False,
            options=options,
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
            # A prior summary is not the "original" user message.
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


def _serialize_messages(messages: list[dict]) -> str:
    """Serialize a list of messages into readable text for summarization."""
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content") or ""

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                # Summarize tool calls compactly
                tool_names = []
                for tc in tool_calls:
                    fn = getattr(tc, "function", None) or tc.get("function", {})
                    name = getattr(fn, "name", None) or fn.get("name", "unknown")
                    tool_names.append(name)
                tools_str = ", ".join(tool_names)
                if content:
                    lines.append(f"Assistant: {content}\n  [Called tools: {tools_str}]")
                else:
                    lines.append(f"Assistant: [Called tools: {tools_str}]")
            elif content:
                lines.append(f"Assistant: {content}")

        elif role == "tool":
            tool_name = msg.get("tool_name", "unknown")
            # Truncate long tool results for the summary prompt
            preview = content[:500] if len(content) > 500 else content
            suffix = f"... [{len(content)} chars total]" if len(content) > 500 else ""
            lines.append(f"Tool ({tool_name}): {preview}{suffix}")

        elif role == "user":
            # Skip prior summary messages — handled separately via
            # _extract_prior_summary so the LLM merges facts explicitly.
            if content.startswith(_SUMMARY_PREFIX):
                continue
            lines.append(f"User: {content}")

    return "\n\n".join(lines)
