"""LoopDetector hook — detects repeated identical tool-call rounds."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class LoopDetector:
    """Detects when the model repeats the same tool-call signature N rounds in a row."""

    def __init__(self, threshold: int = 10) -> None:
        """Initialize with the number of identical rounds that triggers a nudge."""
        self._threshold = threshold
        self._recent: list[str] = []
        self._current_round: list[tuple[str, dict[str, Any]]] = []
        self._lock = asyncio.Lock()

    def after_tool(
        self,
        tool_name: str,
        tool_arguments: dict[str, Any],
        tool_result: str,
    ) -> str:
        """Accumulate (tool_name, arguments) pairs for the current round."""
        # after_tool is sync — can't await lock. Use list append which is
        # atomic under CPython's GIL for asyncio (single-threaded event loop).
        self._current_round.append((tool_name, tool_arguments))
        return tool_result

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Finalize the previous round's signature and check for repetition."""
        async with self._lock:
            if not self._current_round:
                return
            sig_json = json.dumps(self._current_round, sort_keys=True)
            sig_hash = hashlib.sha256(sig_json.encode()).hexdigest()
            self._current_round = []
            self._recent.append(sig_hash)
            if len(self._recent) > self._threshold:
                self._recent.pop(0)
            if len(self._recent) == self._threshold and len(set(self._recent)) == 1:
                logger.warning(
                    "Agent '%s' stuck in loop: same tool call %d times in a row",
                    agent_name,
                    self._threshold,
                )
                self._recent.clear()
                history.append(
                    {
                        "role": "user",
                        "content": (
                            "You are repeating the same tool call without making progress. "
                            "Try a different approach, use a different tool, or change your arguments. "
                            "If the current approach isn't working, move on to the next step."
                        ),
                    }
                )
