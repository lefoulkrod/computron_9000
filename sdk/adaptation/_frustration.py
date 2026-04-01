"""Frustration detection using pattern matching and scoring."""

import re
from dataclasses import dataclass
from enum import Enum, auto


class FrustrationLevel(Enum):
    """User frustration levels from user input analysis."""

    NONE = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


@dataclass
class FrustrationResult:
    """Result of frustration detection."""

    level: FrustrationLevel
    score: float  # 0.0 to 1.0
    matched_patterns: list[str]

    def is_frustrated(self) -> bool:
        """Return True if user shows signs of frustration."""
        return self.level in (FrustrationLevel.LOW, FrustrationLevel.MEDIUM, FrustrationLevel.HIGH)


class FrustrationDetector:
    """Detects user frustration from message patterns."""

    # Patterns grouped by intensity level
    _PATTERNS = {
        FrustrationLevel.HIGH: [
            r"\b(stupid|idiot|useless|broken|garbage|trash|hate)\b",
            r"\b(waste of time|not working|doesn't work|never works)\b",
            r"(?!.*\?)\bf\s*[!1]*\b",  # F-word as exclamation
            r"\b(suck|sucks|pathetic|terrible|awful|worst)\b",
            r"[!]{3,}",  # Multiple exclamation marks
        ],
        FrustrationLevel.MEDIUM: [
            r"\b(annoying|frustrating|confused|confusing|unclear)\b",
            r"\b(not helping|not useful|not what i wanted)\b",
            r"\b(again|still|always)\s+(not|wrong|broken|failing)\b",
            r"\bwhy (can't|won't|doesn't|isn't)\b",
            r"\b(expected|should have|supposed to)\b",
            r"[!]{2}",  # Double exclamation
        ],
        FrustrationLevel.LOW: [
            r"\b(hmm|uh|um)\s*\?*\s*$",  # Uncertainty at end
            r"\b(didn't|did not) (work|help|fix)\b",
            r"\b(still|yet)\s+(waiting|trying|issue|problem)\b",
            r"\b(any|anyone|someone)\s*\?",  # Seeking help
        ],
    }

    # Scoring weights for each level
    _SCORES = {
        FrustrationLevel.HIGH: 0.8,
        FrustrationLevel.MEDIUM: 0.5,
        FrustrationLevel.LOW: 0.2,
    }

    def __init__(self, case_sensitive: bool = False):
        """Initialize detector with optional case sensitivity."""
        self.case_sensitive = case_sensitive
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict[FrustrationLevel, list[re.Pattern]]:
        """Compile regex patterns for efficient matching."""
        flags = 0 if self.case_sensitive else re.IGNORECASE
        return {
            level: [re.compile(p, flags) for p in patterns]
            for level, patterns in self._PATTERNS.items()
        }

    def detect(self, message: str) -> FrustrationResult:
        """Analyze message and return frustration level.

        Args:
            message: User's input message.

        Returns:
            FrustrationResult with level, score, and matched patterns.
        """
        matched = []
        total_score = 0.0

        for level, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(message):
                    matched.append(pattern.pattern)
                    total_score += self._SCORES[level]

        # Normalize score to 0-1 range (cap at 1.0)
        final_score = min(total_score, 1.0)

        # Determine level based on score
        if final_score >= 0.8:
            level = FrustrationLevel.HIGH
        elif final_score >= 0.5:
            level = FrustrationLevel.MEDIUM
        elif final_score > 0:
            level = FrustrationLevel.LOW
        else:
            level = FrustrationLevel.NONE

        return FrustrationResult(
            level=level,
            score=final_score,
            matched_patterns=matched,
        )


# Singleton instance for reuse
_default_detector = FrustrationDetector()


def detect_frustration(message: str) -> FrustrationResult:
    """Convenience function using default detector."""
    return _default_detector.detect(message)
