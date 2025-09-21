"""Shared exception types for browser tools.

The goal is to provide a single, semantically clear exception ``BrowserToolError``
that all browser-related tool functions raise on user-visible failures. This
unification simplifies upstream error handling (agents, REPLs, web server) by
allowing a single except clause while still preserving underlying exception
context via exception chaining (``raise ... from exc``).  The original
exception is always attached as ``__cause__``.

Usage pattern inside a tool implementation::

    try:
        ... do playwright / model work ...
    except SomeSpecificLibError as exc:
        raise BrowserToolError("Meaningful message") from exc

Callers should catch ``BrowserToolError`` for any recoverable, user-actionable
issues (e.g., navigation problems, invalid selectors, model failures).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BrowserToolError(Exception):
    """Generic failure raised by any browser tool.

    Attributes:
        message: Human-readable description of the failure, suitable for
            conveying to the calling agent/model so it can adjust behavior.
        tool: Optional short tool identifier (e.g. ``open_url``) for easier
            routing or metrics. Purely informational.
        details: Optional structured dictionary with extra context. Must be
            JSON-serializable if provided.
    """

    def __init__(
        self,
        message: str,
        *,
        tool: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a ``BrowserToolError``.

        Args:
            message: Human-readable failure description.
            tool: Optional short identifier of the tool raising the error.
            details: Optional JSON-serializable extra context for diagnostics.
        """
        super().__init__(message)
        self.message = message
        self.tool = tool
        self.details = details or {}

    def __str__(self) -> str:
        """Return a concise string representation with optional tool + details."""
        base = self.message
        if self.tool:
            base = f"[{self.tool}] {base}"
        if self.details:
            try:
                extras = ", ".join(f"{k}={v!r}" for k, v in self.details.items())
            except RuntimeError:  # pragma: no cover - defensive narrow case
                extras = "<unprintable details>"
            base = f"{base} ({extras})"
        return base


__all__ = ["BrowserToolError"]
