"""Shared env-var bootstrapping for broker entry points.

Every concrete broker reads its config from the environment the supervisor
passes at spawn time. The two primitives below keep each broker's ``__main__``
tiny and ensure a consistent contract with the supervisor:

- Missing required env var exits with :data:`integrations.brokers._common._exit_codes.GENERIC_ERROR`
  and a clear message — the supervisor turns non-auth-fail exits into the
  ``error`` state with backoff restart.
- Boolean flags are parsed fail-closed. Only the literal string ``"true"``
  (case-insensitive) is truthy, so a typo or missing flag defaults to the safe
  side (e.g. ``WRITE_ALLOWED`` defaults to no writes).
"""

from __future__ import annotations

import logging
import os
import sys

from integrations.brokers._common._exit_codes import GENERIC_ERROR

logger = logging.getLogger(__name__)


def env_required(name: str) -> str:
    """Return the env var or exit :data:`GENERIC_ERROR` with a clear message.

    Never raises — a missing required env var means the supervisor misspawned
    the broker, and failing fast with a useful log line is more helpful than
    propagating a KeyError up through the entrypoint.
    """
    value = os.environ.get(name)
    if value is None:
        logger.error("missing required env var: %s", name)
        sys.exit(GENERIC_ERROR)
    return value


def parse_bool(value: str) -> bool:
    """Parse a ``true``/``false`` string, fail-closed.

    Accepts the plain ``"true"`` / ``"false"`` forms the supervisor sends
    (not ``"1"``, ``"yes"``, etc. — intentionally narrow to keep the contract
    obvious). Anything that isn't literally ``"true"`` (case-insensitive) is
    treated as false.
    """
    return value.strip().lower() == "true"
