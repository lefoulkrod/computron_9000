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

To add a new prerequisite, add a check to ``is_ready()`` in ``_gate.py``.
"""

from setup._gate import is_ready, mark_ready

__all__ = ["is_ready", "mark_ready"]
