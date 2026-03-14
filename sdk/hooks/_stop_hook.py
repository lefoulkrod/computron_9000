"""StopHook — checks for user-requested stop at before_model and after_model phases."""

from __future__ import annotations

from typing import Any

from sdk.loop import StopRequestedError, check_stop


class StopHook:
    """Checks for user-requested stop at before_model and after_model phases."""

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Raise ``StopRequestedError`` if the user requested a stop."""
        check_stop()

    async def after_model(
        self, response: Any, history: Any, iteration: int, agent_name: str
    ) -> Any:
        """Strip tool calls and raise ``StopRequestedError`` on stop request."""
        try:
            check_stop()
        except StopRequestedError:
            # Strip tool_calls so the assistant message won't have dangling calls
            if hasattr(response, "message") and hasattr(response.message, "tool_calls"):
                response.message.tool_calls = None
            history.append({
                "role": "user",
                "content": "The user has requested to stop. Wrap up your response.",
            })
            raise
        return response
