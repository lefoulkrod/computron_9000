"""Hook that records conversation turns for later skill extraction."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from tools.conversations import (
    ConversationMetadata,
    ConversationRecord,
    ToolCallRecord,
    TurnRecord,
    save_conversation,
    update_conversation_metadata,
)

logger = logging.getLogger(__name__)

# Maximum length for tool result summaries stored in the record.
_MAX_RESULT_LEN = 500


class ConversationRecorderHook:
    """Accumulates turn data and persists a ConversationRecord on completion.

    Attach this hook to the top-level agent only — sub-agent conversations
    are captured via depth and agent_name fields on events.
    """

    def __init__(
        self,
        *,
        user_message: str,
        agent_name: str,
        model: str,
        session_id: str = "default",
        summary_model: str | None = None,
    ) -> None:
        self._conversation_id = str(uuid.uuid4())
        self._user_message = user_message
        self._agent_name = agent_name
        self._model = model
        self._session_id = session_id
        self._summary_model = summary_model
        self._started_at = datetime.now(UTC).isoformat()
        self._turns: list[TurnRecord] = []
        self._current_tool_calls: list[ToolCallRecord] = []
        self._tool_start_time: float | None = None
        self._agent_chain: list[str] = [agent_name]
        self._total_tool_calls = 0
        self._last_content: str | None = None
        self._last_thinking: str | None = None

    @property
    def conversation_id(self) -> str:
        """The ID of the conversation being recorded."""
        return self._conversation_id

    async def after_model(
        self,
        response: Any,
        history: Any,
        iteration: int,
        agent_name: str,
    ) -> Any:
        """Record assistant content and tool calls from the model response."""
        content = response.message.content
        thinking = response.message.thinking
        tool_calls = response.message.tool_calls

        self._last_content = content
        self._last_thinking = thinking

        # Track agent chain
        if agent_name not in self._agent_chain:
            self._agent_chain.append(agent_name)

        if tool_calls:
            self._current_tool_calls = []
            for tc in tool_calls:
                self._current_tool_calls.append(
                    ToolCallRecord(
                        name=tc.function.name,
                        arguments=tc.function.arguments or {},
                    )
                )

        self._turns.append(
            TurnRecord(
                role="assistant",
                content=content,
                thinking=thinking,
                tool_calls=list(self._current_tool_calls),
                agent_name=agent_name,
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

        return response

    def before_tool(
        self, tool_name: str | None, tool_arguments: dict[str, Any]
    ) -> str | None:
        """Record tool call start time."""
        self._tool_start_time = time.monotonic()
        self._total_tool_calls += 1
        return None

    def after_tool(
        self, tool_name: str | None, tool_arguments: dict[str, Any], tool_result: str
    ) -> str:
        """Record tool result and duration."""
        duration_ms = None
        if self._tool_start_time is not None:
            duration_ms = int((time.monotonic() - self._tool_start_time) * 1000)
            self._tool_start_time = None

        # Truncate result for storage
        result_summary = tool_result[:_MAX_RESULT_LEN] if tool_result else ""
        success = not tool_result.startswith(("Error", "Tool not found", "Argument validation failed"))

        self._turns.append(
            TurnRecord(
                role="tool",
                content=result_summary,
                agent_name=None,
                timestamp=datetime.now(UTC).isoformat(),
                tool_calls=[
                    ToolCallRecord(
                        name=tool_name or "unknown",
                        arguments=tool_arguments,
                        result_summary=result_summary,
                        duration_ms=duration_ms,
                        success=success,
                    )
                ],
            )
        )
        return tool_result

    def finalize(self) -> ConversationRecord:
        """Build and persist the final ConversationRecord."""
        ended_at = datetime.now(UTC).isoformat()
        started = datetime.fromisoformat(self._started_at)
        ended = datetime.fromisoformat(ended_at)
        duration = (ended - started).total_seconds()

        record = ConversationRecord(
            id=self._conversation_id,
            session_id=self._session_id,
            started_at=self._started_at,
            ended_at=ended_at,
            model=self._model,
            agent=self._agent_name,
            user_message=self._user_message,
            turns=self._turns,
            metadata=ConversationMetadata(
                total_tool_calls=self._total_tool_calls,
                agent_chain=self._agent_chain,
                duration_seconds=duration,
            ),
        )

        try:
            save_conversation(record)
            logger.info("Saved conversation record %s", self._conversation_id)
        except Exception:
            logger.exception("Failed to save conversation record %s", self._conversation_id)

        return record

    def classify_outcome_async(self) -> None:
        """Kick off an async outcome classification (non-blocking).

        Uses a lightweight LLM call to classify the conversation outcome
        as SUCCESS, FAILURE, or PARTIAL. Falls back to "unknown" on error.
        """
        if not self._summary_model:
            return

        conversation_id = self._conversation_id
        user_message = self._user_message
        final_content = self._last_content or ""
        model = self._summary_model

        async def _classify() -> None:
            try:
                from models.generate_completion import generate_completion

                prompt = (
                    "Given this conversation between a user and an AI assistant, "
                    "classify the outcome.\n"
                    f'User request: "{user_message}"\n'
                    f'Final assistant response: "{final_content[:1000]}"\n'
                    "Did the assistant successfully complete the user's request?\n"
                    "Reply with exactly one word: SUCCESS, FAILURE, or PARTIAL"
                )
                result, _ = await generate_completion(prompt, model)
                outcome_word = result.strip().upper()
                if outcome_word in ("SUCCESS", "FAILURE", "PARTIAL"):
                    outcome = outcome_word.lower()
                else:
                    outcome = "unknown"
                update_conversation_metadata(conversation_id, outcome=outcome)
                logger.info("Classified conversation %s outcome: %s", conversation_id, outcome)
            except Exception:
                logger.exception("Failed to classify conversation %s outcome", conversation_id)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_classify())
        except RuntimeError:
            logger.debug("No running event loop for outcome classification")
