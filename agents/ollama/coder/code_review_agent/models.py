"""Code review models.

Defines the result type returned by the code review agent after validating
whether a coder step implementation appears correct.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CodeReviewResult(BaseModel):
    """Outcome of reviewing a single step implementation.

    Args:
        passed: True if the step appears correctly implemented; otherwise False.
        fixes: Actionable fixes to address gaps when ``passed`` is False.
    """

    passed: bool = Field(serialization_alias="pass")
    fixes: list[str] = Field(default_factory=list)


__all__ = [
    "CodeReviewResult",
]
