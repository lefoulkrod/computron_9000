"""Hook that records turn data for later skill extraction."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from conversations import (
    MessageRecord,
    ToolCallRecord,
    TurnMetadata,
    TurnRecord,
    save_turn,
)

logger = logging.getLogger(__name__)


class TurnRecorderHook:
    """Accumulates message data and persists a TurnRecord on completion.

    Attach this hook to the top-level agent only — sub-agent turns
    are captured via depth and agent_name fields on events.
    """

    def __init__(
        self,
        *,
        user_message: str,
        agent_name: str,
        model: str,
        conversation_id: str = "default",
        summary_model: str | None = None,
    ) -> None:
        self._turn_id = str(uuid.uuid4())
        self._user_message = user_message
        self._agent_name = agent_name
        self._model = model
        self._conversation_id = conversation_id
        self._summary_model = summary_model
        self._started_at = datetime.now(UTC).isoformat()
        self._messages: list[MessageRecord] = []
        self._current_tool_calls: list[ToolCallRecord] = []
        self._tool_start_times: dict[str, float] = {}
        self._agent_chain: list[str] = [agent_name]
        self._total_tool_calls = 0
        self._applied_skill: str | None = None
        self._lock = asyncio.Lock()
        self._last_content: str | None = None
        self._last_thinking: str | None = None

    @property
    def turn_id(self) -> str:
        """The ID of the turn being recorded."""
        return self._turn_id

    @property
    def conversation_id(self) -> str:
        """The conversation this turn belongs to."""
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

        self._messages.append(
            MessageRecord(
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
        # Use tool_name as key — safe for parallel since each tool call
        # gets its own before/after pair even if names overlap (timing
        # may be slightly off for duplicate names but won't crash)
        key = f"{tool_name}_{id(tool_arguments)}"
        self._tool_start_times[key] = time.monotonic()
        self._total_tool_calls += 1
        return None

    def after_tool(
        self, tool_name: str | None, tool_arguments: dict[str, Any], tool_result: str
    ) -> str:
        """Record tool result and duration, and detect skill application."""
        key = f"{tool_name}_{id(tool_arguments)}"
        duration_ms = None
        start = self._tool_start_times.pop(key, None)
        if start is not None:
            duration_ms = int((time.monotonic() - start) * 1000)

        # Track skill application
        if tool_name == "apply_skill" and "skill_name" in tool_arguments:
            self._applied_skill = tool_arguments["skill_name"]
            logger.info("Skill applied: %s", self._applied_skill)
            try:
                from skills import record_skill_used

                record_skill_used(self._applied_skill)
            except Exception:
                logger.exception("Failed to record usage for skill '%s'", self._applied_skill)

        # Store full tool results (no truncation)
        result_summary = tool_result or ""
        success = not tool_result.startswith(("Error", "Tool not found", "Argument validation failed"))

        self._messages.append(
            MessageRecord(
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

    def on_turn_end(self, final_content: str | None, agent_name: str) -> None:
        """Finalize and persist the turn record."""
        self.finalize()

    def finalize(self) -> TurnRecord:
        """Build and persist the final TurnRecord."""
        ended_at = datetime.now(UTC).isoformat()
        started = datetime.fromisoformat(self._started_at)
        ended = datetime.fromisoformat(ended_at)
        duration = (ended - started).total_seconds()

        record = TurnRecord(
            id=self._turn_id,
            conversation_id=self._conversation_id,
            started_at=self._started_at,
            ended_at=ended_at,
            model=self._model,
            agent=self._agent_name,
            user_message=self._user_message,
            messages=self._messages,
            metadata=TurnMetadata(
                total_tool_calls=self._total_tool_calls,
                agent_chain=self._agent_chain,
                duration_seconds=duration,
                skill_applied=self._applied_skill,
            ),
        )

        try:
            save_turn(record)
            logger.info("Saved turn record %s", self._turn_id)
        except Exception:
            logger.exception("Failed to save turn record %s", self._turn_id)

        return record
