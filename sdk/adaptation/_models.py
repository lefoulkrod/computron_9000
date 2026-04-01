"""Data models for user adaptation state."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sdk.adaptation._frustration import FrustrationLevel


@dataclass
class UserState:
    """Tracks the current emotional/adaptive state of the user."""

    frustration_level: FrustrationLevel = FrustrationLevel.NONE
    frustration_score: float = 0.0
    last_message_timestamp: Optional[datetime] = field(default_factory=datetime.utcnow)
    consecutive_frustrated_turns: int = 0

    def update_frustration(self, level: FrustrationLevel, score: float) -> None:
        """Update frustration tracking."""
        if level != FrustrationLevel.NONE:
            self.consecutive_frustrated_turns += 1
        else:
            self.consecutive_frustrated_turns = 0

        self.frustration_level = level
        self.frustration_score = score
        self.last_message_timestamp = datetime.utcnow()

    def get_adaptation_instructions(self) -> str:
        """Generate instructions based on current state."""
        if self.frustration_level == FrustrationLevel.HIGH or self.consecutive_frustrated_turns >= 2:
            return self._HIGH_FRUSTRATION_INSTRUCTIONS
        elif self.frustration_level == FrustrationLevel.MEDIUM:
            return self._MEDIUM_FRUSTRATION_INSTRUCTIONS
        elif self.frustration_level == FrustrationLevel.LOW:
            return self._LOW_FRUSTRATION_INSTRUCTIONS
        return ""

    _HIGH_FRUSTRATION_INSTRUCTIONS = """
    [FRUSTRATION ADAPTATION - HIGH]
    The user appears highly frustrated. Respond with:
    1. IMMEDIATE ACKNOWLEDGMENT: "I understand this is frustrating" or similar empathy
    2. CONCISE DIRECT ANSWER: No preamble, get straight to the solution
    3. STEP-BY-STEP: Numbered, actionable steps only
    4. NO EXCUSES: Don't explain why things went wrong, focus on fixing
    5. CONFIDENCE: State solutions definitively, avoid hedging ("maybe", "perhaps")
    """

    _MEDIUM_FRUSTRATION_INSTRUCTIONS = """
    [FRUSTRATION ADAPTATION - MEDIUM]
    The user appears somewhat frustrated. Respond with:
    1. Brief acknowledgment of the difficulty
    2. Clear, direct explanation
    3. Actionable next steps
    4. Avoid unnecessary verbosity
    """

    _LOW_FRUSTRATION_INSTRUCTIONS = """
    [FRUSTRATION ADAPTATION - LOW]
    The user may be slightly confused or stuck. Respond with:
    1. Patient, helpful tone
    2. Offer clarification proactively
    """
