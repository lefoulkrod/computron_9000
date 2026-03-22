"""NudgeHook — drains queued nudge messages and injects them into history."""

from __future__ import annotations

import logging
from typing import Any

from sdk.events import get_current_depth
from sdk.turn import drain_nudges

logger = logging.getLogger(__name__)


class NudgeHook:
    """Drains queued nudge messages and injects them into the conversation history.

    Only drains nudges for the root agent (depth 0). Sub-agents skip draining
    to prevent them from stealing nudges intended for the root.
    """

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Append any queued nudge messages as a single user message."""
        # Only the root agent (depth 0) should drain nudges.
        # Sub-agents inherit the conversation_id ContextVar and would
        # otherwise steal nudges meant for the root.
        if get_current_depth() > 0:
            logger.debug("Skipping nudge drain for sub-agent '%s' at depth %d", agent_name, get_current_depth())
            return

        nudges = drain_nudges()
        if nudges:
            combined = "\n\n".join(nudges)
            history.append({"role": "user", "content": combined})
            logger.info("Injected %d nudge(s) for agent '%s'", len(nudges), agent_name)
