"""NudgeHook — drains queued nudge messages and injects them into history."""

from __future__ import annotations

import logging
from typing import Any

from agents.ollama.sdk.turn import drain_nudges

logger = logging.getLogger(__name__)


class NudgeHook:
    """Drains queued nudge messages and injects them into the conversation history."""

    def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Append any queued nudge messages as a single user message."""
        nudges = drain_nudges()
        if nudges:
            combined = "\n\n".join(nudges)
            history.append({"role": "user", "content": combined})
            logger.info("Injected %d nudge(s) for agent '%s'", len(nudges), agent_name)
