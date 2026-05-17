"""ContextHook — runs context strategies and emits the post-call event."""

from __future__ import annotations

from typing import Any


class ContextHook:
    """Drives the ContextManager around each LLM call."""

    def __init__(self, ctx_manager: Any, max_iterations: int = 0) -> None:
        """Initialize with the context manager that owns the history."""
        self._ctx_manager = ctx_manager
        self._max_iterations = max_iterations

    async def before_model(
        self, history: Any, iteration: int, agent_name: str
    ) -> None:
        """Delegate to the context manager before each LLM call."""
        await self._ctx_manager.before_model()

    async def after_model(
        self, response: Any, history: Any, iteration: int, agent_name: str
    ) -> Any:
        """Delegate to the context manager after each LLM call."""
        await self._ctx_manager.after_model(
            iteration=iteration, max_iterations=self._max_iterations,
        )
        return response
