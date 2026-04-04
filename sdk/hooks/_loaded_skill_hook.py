"""Hook that injects loaded skill prompts into the system message."""

from __future__ import annotations

import logging

from sdk.context import ConversationHistory
from sdk.skills.agent_state import get_active_agent_state

logger = logging.getLogger(__name__)

# Marker used to find and replace the skill section in the system message.
_SKILL_SECTION_MARKER = "\n── Loaded Skills ──"


class LoadedSkillHook:
    """Injects loaded skill prompts into the system message before each model call.

    Reads from the active AgentState to build a skill prompt section and
    appends it to the system message. On each iteration the section is
    rebuilt so newly loaded skills appear immediately. Existing content
    (base instruction, memory) is preserved.
    """

    async def before_model(
        self,
        history: ConversationHistory,
        iteration: int,
        agent_name: str,
    ) -> None:
        """Rebuild the skill section of the system message."""
        agent_state = get_active_agent_state()
        if agent_state is None:
            return

        skill_section = agent_state.build_skill_prompt()

        messages = history.messages
        if not messages or messages[0].get("role") != "system":
            return

        current = messages[0]["content"] or ""

        # Strip any existing skill section before appending the current one.
        marker_pos = current.find(_SKILL_SECTION_MARKER)
        if marker_pos >= 0:
            base = current[:marker_pos]
        else:
            base = current

        history.set_system_message(base + skill_section)
