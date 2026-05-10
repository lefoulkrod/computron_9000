"""NudgeHook — drains queued nudge messages and injects them into history."""

from __future__ import annotations

import logging
from typing import Any

from sdk.events import get_current_agent_id
from sdk.turn import drain_nudges

logger = logging.getLogger(__name__)


class NudgeHook:
    """Drains queued nudge messages and injects them into the conversation history.

    Each agent has its own nudge queue keyed by agent ID. The hook drains
    the current agent's queue before each model call.
    """

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Append any queued nudge messages as a single user message."""
        nudges = drain_nudges(get_current_agent_id())
        if nudges:
            combined = "\n\n".join(nudges)
            history.append({"role": "user", "content": combined})
            logger.info("Injected %d nudge(s) for agent '%s'", len(nudges), agent_name)
