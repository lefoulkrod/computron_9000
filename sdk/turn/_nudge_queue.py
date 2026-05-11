"""Per-agent nudge queue storage.

Leaf module with no internal imports — both ``sdk.turn._turn`` and
``sdk.events._context`` can import from here without cycles.
"""

from __future__ import annotations

# Keyed by agent ID (context_id from agent_span).
_nudge_queues: dict[str, list[str]] = {}


def register_nudge_queue(agent_id: str) -> None:
    """Create an empty nudge queue so *agent_id* can receive nudges."""
    _nudge_queues[agent_id] = []


def unregister_nudge_queue(agent_id: str) -> None:
    """Remove the nudge queue for *agent_id*."""
    _nudge_queues.pop(agent_id, None)


def queue_nudge(target_id: str, message: str) -> None:
    """Append a nudge message to the queue for *target_id*."""
    q = _nudge_queues.get(target_id)
    if q is not None:
        q.append(message)


def drain_nudges(agent_id: str | None = None) -> list[str]:
    """Pop and return all queued nudge messages for *agent_id*.

    Returns an empty list if the agent has no queue or no messages.
    """
    if agent_id is None:
        return []
    q = _nudge_queues.get(agent_id)
    if not q:
        return []
    messages = list(q)
    q.clear()
    return messages
