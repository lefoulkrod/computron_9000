"""User adaptation module for detecting and responding to user state."""

from sdk.adaptation._frustration import (
    FrustrationDetector,
    FrustrationLevel,
    FrustrationResult,
    detect_frustration,
)
from sdk.adaptation._models import UserState

__all__ = [
    "FrustrationDetector",
    "FrustrationLevel",
    "FrustrationResult",
    "UserState",
    "detect_frustration",
]
