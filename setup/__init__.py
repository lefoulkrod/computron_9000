"""Setup readiness gate.

Setup is one contributor to the aggregate ``app["ready"]`` event in the
aiohttp app — its specific event lives at ``app["setup_ready"]`` and is
registered by ``server.aiohttp_app._init_setup_signal``.

This module owns the logic for deciding whether setup is done
(``is_ready``) and for firing the contributor event (``mark_ready``).
"""

from setup._gate import is_ready, mark_ready

__all__ = ["is_ready", "mark_ready"]
