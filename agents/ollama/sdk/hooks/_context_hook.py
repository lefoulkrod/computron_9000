"""ContextHook — records token usage from model responses."""

from __future__ import annotations

from typing import Any


class ContextHook:
    """Records token usage from model responses via a ContextManager."""

    def __init__(self, ctx_manager: Any) -> None:
        """Initialize with the context manager that tracks token usage."""
        self._ctx_manager = ctx_manager

    def after_model(
        self, response: Any, history: Any, iteration: int, agent_name: str
    ) -> Any:
        """Record token usage from the response."""
        self._ctx_manager.record_response(response)
        return response
