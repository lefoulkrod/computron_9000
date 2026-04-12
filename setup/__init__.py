"""Setup readiness gate.

Subsystems that need user-driven setup to complete before they can run
(e.g. the task runner) wait on an ``asyncio.Event`` that lives on the
aiohttp app.  This module owns the logic for deciding whether setup is
done and for firing that signal.

Typical startup flow::

    # 1. create_app() stores the event
    app["ready"] = asyncio.Event()

    # 2. After migrations, check if we're already good
    if setup.is_ready():
        app["ready"].set()

    # 3. Subsystems await the event in background tasks
    await app["ready"].wait()

    # 4. When the setup wizard finishes, the settings handler calls
    setup.mark_ready(app)

To add a new prerequisite, add a check to ``is_ready()``.
"""

from __future__ import annotations

import logging
from typing import Any

from settings import load_settings

logger = logging.getLogger(__name__)

_READY_KEY = "ready"


def is_ready() -> bool:
    """Return True if all setup prerequisites are satisfied."""
    if not load_settings().get("setup_complete"):
        return False
    return True


def mark_ready(app: Any) -> None:
    """Signal that setup is complete, firing the ready event.

    Re-checks ``is_ready()`` before firing so that the event only
    triggers when *all* prerequisites are met.

    Args:
        app: The aiohttp application (dict-like) holding the ready event.
    """
    if not is_ready():
        logger.warning("mark_ready called but is_ready() is False — ignoring")
        return
    event = app.get(_READY_KEY)
    if event is None:
        logger.warning("No ready event on app — mark_ready is a no-op")
        return
    if not event.is_set():
        logger.info("Setup complete — signalling ready")
        event.set()


__all__ = ["is_ready", "mark_ready"]
