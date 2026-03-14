"""BudgetGuard hook — appends a nudge when the iteration budget is exceeded."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BudgetGuard:
    """Appends a nudge message when the iteration budget is exceeded."""

    def __init__(self, max_iterations: int) -> None:
        """Initialize with the maximum number of iterations allowed."""
        self._max = max_iterations
        self._exhausted = False

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Append a budget-exhaustion nudge if over the iteration limit."""
        if self._max <= 0 or self._exhausted:
            return
        if iteration > self._max:
            self._exhausted = True
            logger.warning(
                "Agent '%s' hit max_iterations (%d), forcing stop",
                agent_name,
                self._max,
            )
            history.append({
                "role": "user",
                "content": (
                    f"Tool call budget exhausted ({self._max} iterations). "
                    "Wrap up and respond with the information you have."
                ),
            })
