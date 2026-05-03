"""Ready-signal implementation for the setup gate."""

from __future__ import annotations

import logging
from typing import Any

from settings import load_settings

logger = logging.getLogger(__name__)

_SETUP_READY_KEY = "setup_ready"


def is_ready() -> bool:
    """Return True if all setup prerequisites are satisfied."""
    if not load_settings().get("setup_complete"):
        return False
    return True


def mark_ready(app: Any) -> None:
    """Signal that setup is complete, firing the setup-ready contributor event.

    Re-checks ``is_ready()`` before firing so that the event only
    triggers when *all* prerequisites are met.

    Args:
        app: The aiohttp application holding ``app["setup_ready"]``.

    """
    if not is_ready():
        logger.warning("mark_ready called but is_ready() is False — ignoring")
        return
    event = app.get(_SETUP_READY_KEY)
    if event is None:
        logger.warning("No setup_ready event on app — mark_ready is a no-op")
        return
    if not event.is_set():
        logger.info("Setup complete — signalling setup-ready")
        event.set()
