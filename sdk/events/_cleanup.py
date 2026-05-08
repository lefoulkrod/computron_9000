"""Agent span exit hook registry.

Tools that allocate per-agent resources register a cleanup callback here.
The SDK calls these when an agent span exits, without needing to know which
tools exist or what they allocated.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

AgentSpanExitHook = Callable[[str], Awaitable[None]]

_hooks: list[AgentSpanExitHook] = []


def register_agent_span_exit_hook(fn: AgentSpanExitHook) -> None:
    """Register a callback to run when any agent span completes."""
    _hooks.append(fn)


async def run_agent_span_exit_hooks(context_id: str) -> None:
    """Run all registered exit hooks for the given agent context."""
    for fn in _hooks:
        try:
            await fn(context_id)
        except Exception:  # noqa: BLE001
            logger.debug("Agent span exit hook %s failed for '%s'", fn.__name__, context_id)
