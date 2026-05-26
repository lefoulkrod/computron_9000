"""StopHook — checks for user-requested stop at before_model and after_model phases."""

from __future__ import annotations

from typing import Any

from sdk.turn import StopRequestedError, check_stop


class StopHook:
    """Checks for user-requested stop at before_model and after_model phases."""

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Raise ``StopRequestedError`` if the user requested a stop."""
        check_stop()

    async def after_model(
        self, response: Any, history: Any, iteration: int, agent_name: str
    ) -> Any:
        """Strip tool calls and append a nudge on stop request.

        Does **not** raise ``StopRequestedError`` here — raising would skip
        the assistant-message append in :func:`run_turn`, losing the model's
        response content from the conversation history.  Instead we strip
        any tool calls so the turn ends cleanly (no dangling calls) and let
        the next iteration's ``before_model`` raise if the stop event is
        still set.
        """
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
            # Return the modified response — do NOT re-raise.
        return response
