"""Code review models.

Defines the result type returned by the code review agent after validating
whether a coder step implementation appears correct.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CodeReviewResult(BaseModel):
    """Outcome of reviewing a single step implementation.

    Args:
        success: True if the step appears correctly implemented; otherwise False.
        required_changes: Actionable fixes to address gaps when ``success`` is False.
    """

    success: bool
    required_changes: list[str] = Field(default_factory=list)


__all__ = [
    "CodeReviewResult",
]
