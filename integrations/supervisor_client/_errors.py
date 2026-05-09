"""Exception raised by ``supervisor_client.call``.

``SupervisorError`` carries the ``code`` and ``message`` from the
supervisor's error response frame so callers can branch on the code
(e.g. map to HTTP statuses) without parsing raw dicts.
"""

from __future__ import annotations


class SupervisorError(Exception):
    """The supervisor returned a structured error for a verb call."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
