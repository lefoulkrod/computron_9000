"""ContextHook — records token usage and runs context strategies."""

from __future__ import annotations

from typing import Any


class ContextHook:
    """Records token usage and runs context strategies via a ContextManager."""

    def __init__(self, ctx_manager: Any, max_iterations: int = 0) -> None:
        """Initialize with the context manager that tracks token usage."""
        self._ctx_manager = ctx_manager
        self._max_iterations = max_iterations

    async def before_model(
        self, history: Any, iteration: int, agent_name: str
    ) -> None:
        """Run before-model context strategies."""
        await self._ctx_manager.apply_strategies()

    async def after_model(
        self, response: Any, history: Any, iteration: int, agent_name: str
    ) -> Any:
        """Record token usage from the response."""
        await self._ctx_manager.record_response(
            response, iteration=iteration, max_iterations=self._max_iterations,
        )
        return response
