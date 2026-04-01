"""Hook for injecting frustration-aware instructions into prompts."""

from __future__ import annotations

from typing import Any

from sdk.adaptation import UserState
from sdk.events import AgentEvent, UserStatePayload, publish_event


class FrustrationHook:
    """Hook that adapts prompts based on detected user frustration."""

    def __init__(self, user_state: UserState | None = None):
        """Initialize with optional user state (creates new if None)."""
        self._user_state = user_state or UserState()

    @property
    def user_state(self) -> UserState:
        """Access the current user state."""
        return self._user_state

    async def before_model(
        self, history: Any, iteration: int, agent_name: str
    ) -> None:
        """Called before model invocation.

        Injects frustration-aware instructions into system message
        if user is frustrated.
        """
        instructions = self._user_state.get_adaptation_instructions()

        if instructions and hasattr(history, 'append_system_context'):
            history.append_system_context(instructions)

        # Publish user state event for UI awareness
        publish_event(AgentEvent(payload=UserStatePayload(
            type="user_state",
            frustration_level=self._user_state.frustration_level.name.lower(),
            frustration_score=self._user_state.frustration_score,
            consecutive_frustrated_turns=self._user_state.consecutive_frustrated_turns,
        )))
