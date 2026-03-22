"""Context-bound event publishing utilities for the events layer.

This module exposes an asyncio-friendly API to publish AssistantResponse events
without passing dispatcher handles through every call. It relies on a
contextvars.ContextVar to track the currently active dispatcher for the
duration of a single conversation turn.

Guidelines:
- No blocking calls; publishing delegates to the active dispatcher, which is
  responsible for scheduling subscriber callbacks appropriately.
- Safe no-op behavior when no dispatcher is set (useful in tests or
  components that are not running under the message handling flow).
"""

from __future__ import annotations

import itertools
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Avoid runtime import cycles; only needed for typing
    from collections.abc import Generator

from agents.types import LLMOptions

from ._dispatcher import EventDispatcher
from ._models import AgentCompletedPayload, AgentStartedPayload, AssistantResponse

logger = logging.getLogger(__name__)


# Active dispatcher for the current coroutine context.
_current_dispatcher: ContextVar[EventDispatcher | None] = ContextVar(
    "assistant_events_current_dispatcher", default=None
)


# Stack of (context_id, agent_name) frames for nested agent/tool executions.
_context_stack: ContextVar[tuple[tuple[str, str | None], ...]] = ContextVar(
    "assistant_events_context_stack", default=()
)

# LLM options propagated from the user's UI selection for the current turn.
_model_options: ContextVar[LLMOptions | None] = ContextVar("assistant_events_model_options", default=None)

def get_model_options() -> LLMOptions | None:
    """Return the LLM options set for the current request context, or None."""
    return _model_options.get()


def set_model_options(options: LLMOptions | None) -> None:
    """Set the LLM options for the current request context."""
    _model_options.set(options)


_subcontext_counter = itertools.count(1)
_ROOT_CONTEXT_ID = "root"


def _make_child_context_id(label: str | None = None) -> str:
    """Create a child context id derived from the current stack top."""
    stack = _context_stack.get()
    parent_id = stack[-1][0] if stack else _ROOT_CONTEXT_ID
    raw = (label or "child").lower()
    safe = "".join(c if c.isalnum() else "_" for c in raw).strip("_") or "child"
    return f"{parent_id}.{safe}.{next(_subcontext_counter)}"


def get_current_agent_name() -> str | None:
    """Return the agent name from the top of the context stack, or None."""
    stack = _context_stack.get()
    return stack[-1][1] if stack else None


def get_current_agent_id() -> str | None:
    """Return the context id from the top of the context stack, or None."""
    stack = _context_stack.get()
    return stack[-1][0] if stack else None


def get_current_dispatcher() -> EventDispatcher | None:
    """Return the active event dispatcher for the current context, or None."""
    return _current_dispatcher.get()


def get_current_depth() -> int:
    """Return the current nesting depth (0 = root, 1+ = sub-agents)."""
    stack = _context_stack.get()
    return max(0, len(stack) - 1) if stack else 0


@contextmanager
def agent_span(
    agent_name: str | None = None,
    instruction: str | None = None,
) -> Generator[str, None, None]:
    """Push an attribution frame for the duration of the block.

    Events published inside will be tagged with the given agent name and an
    incremented depth. Emits agent lifecycle events on entry and exit.

    Args:
        agent_name: Human-readable agent name for event attribution.
        instruction: The instruction or user message this agent was given.

    Yields:
        str: The context id pushed onto the stack.

    Example:
        with agent_span("Browser Agent", instruction="Browse example.com"):
            publish_event(AssistantResponse(thinking="Navigating..."))
    """
    stack = _context_stack.get()
    parent_id = stack[-1][0] if stack else None
    context_id = _make_child_context_id(agent_name)
    depth = len(stack)
    token = _context_stack.set((*stack, (context_id, agent_name)))

    logger.info(
        "Agent started: %s (id=%s, parent=%s, depth=%d)",
        agent_name, context_id, parent_id, depth,
    )

    publish_event(AssistantResponse(event=AgentStartedPayload(
        type="agent_started",
        agent_id=context_id,
        agent_name=agent_name or "",
        parent_agent_id=parent_id,
        instruction=instruction,
    )))

    status = "success"
    try:
        yield context_id
    except Exception as exc:
        # Import here to avoid circular dependency with sdk.turn
        from sdk.turn._turn import StopRequestedError
        status = "stopped" if isinstance(exc, StopRequestedError) else "error"
        raise
    finally:
        logger.info(
            "Agent completed: %s (id=%s, status=%s, depth=%d)",
            agent_name, context_id, status, depth,
        )
        publish_event(AssistantResponse(event=AgentCompletedPayload(
            type="agent_completed",
            agent_id=context_id,
            agent_name=agent_name or "",
            status=status,
        )))
        _context_stack.reset(token)


def publish_event(event: AssistantResponse) -> None:
    """Publish an AssistantResponse via the dispatcher bound to this context.

    No-op when no dispatcher is set. The event is enriched with the current
    agent name and depth from the context stack before dispatch.

    Args:
        event: The AssistantResponse instance to publish.
    """
    dispatcher = _current_dispatcher.get()
    if dispatcher is None:
        # Intentionally a low-level debug message to avoid noisy logs in contexts
        # where publishing is optional.
        logger.debug("No active dispatcher; dropping event publish request.")
        return

    stack = _context_stack.get()
    try:
        dispatcher.publish(
            event.model_copy(
                update={
                    "agent_name": stack[-1][1] if stack else None,
                    "depth": len(stack) - 1 if stack else 0,
                    "agent_id": stack[-1][0] if stack else None,
                }
            )
        )
    except Exception:  # pragma: no cover - defensive logging path
        logger.exception("Failed to publish AssistantResponse event")
