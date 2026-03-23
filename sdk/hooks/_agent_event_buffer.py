"""Hook that buffers agent lifecycle and preview events for persistence."""

from __future__ import annotations

import logging
from typing import Any

from sdk.events._models import (
    AgentCompletedPayload,
    AgentStartedPayload,
    AssistantResponse,
    BrowserScreenshotPayload,
    FileOutputPayload,
    TerminalOutputPayload,
)

logger = logging.getLogger(__name__)


_MAX_TERMINAL_EVENTS_PER_AGENT = 50


class AgentEventBufferHook:
    """Buffers structural agent events during a turn for persistence.

    Subscribes to the event dispatcher and captures lifecycle events,
    browser screenshots, terminal output, and file outputs. Only keeps
    the last screenshot per agent to limit size, and caps terminal
    events per agent.

    The buffered events are retrieved via ``get_events()`` at turn end
    and passed to the persistence layer.
    """

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._last_screenshots: dict[str, dict[str, Any]] = {}
        self._terminal_counts: dict[str, int] = {}

    def handle_event(self, event: AssistantResponse) -> None:
        """Called by the dispatcher for every published event."""
        if event.event is None:
            return

        agent_id = event.agent_id
        payload = event.event

        if isinstance(payload, AgentStartedPayload):
            self._events.append({
                "type": "agent_started",
                "agent_id": payload.agent_id,
                "agent_name": payload.agent_name,
                "parent_agent_id": payload.parent_agent_id,
                "instruction": payload.instruction,
                "timestamp": event.timestamp.isoformat(),
            })

        elif isinstance(payload, AgentCompletedPayload):
            self._events.append({
                "type": "agent_completed",
                "agent_id": payload.agent_id,
                "agent_name": payload.agent_name,
                "status": payload.status,
                "timestamp": event.timestamp.isoformat(),
            })

        elif isinstance(payload, BrowserScreenshotPayload) and agent_id:
            # Only keep the last screenshot per agent
            self._last_screenshots[agent_id] = {
                "type": "browser_screenshot",
                "agent_id": agent_id,
                "url": payload.url,
                "title": payload.title,
                "screenshot": payload.screenshot,
                "timestamp": event.timestamp.isoformat(),
            }

        elif isinstance(payload, TerminalOutputPayload) and agent_id:
            count = self._terminal_counts.get(agent_id, 0)
            if count < _MAX_TERMINAL_EVENTS_PER_AGENT:
                self._events.append({
                    "type": "terminal_output",
                    "agent_id": agent_id,
                    "cmd_id": payload.cmd_id,
                    "cmd": payload.cmd,
                    "status": payload.status,
                    "stdout": payload.stdout,
                    "stderr": payload.stderr,
                    "exit_code": payload.exit_code,
                    "timestamp": event.timestamp.isoformat(),
                })
                self._terminal_counts[agent_id] = count + 1

        elif isinstance(payload, FileOutputPayload) and agent_id:
            self._events.append({
                "type": "file_output",
                "agent_id": agent_id,
                "filename": payload.filename,
                "content_type": payload.content_type,
                "path": payload.path,
                "timestamp": event.timestamp.isoformat(),
            })

    def get_events(self) -> list[dict[str, Any]]:
        """Return all buffered events including last screenshots per agent."""
        events = list(self._events)
        events.extend(self._last_screenshots.values())
        if events:
            types = {}
            for e in events:
                t = e.get("type", "unknown")
                types[t] = types.get(t, 0) + 1
            logger.debug("Agent event buffer: %d events (%s)", len(events), types)
        return events
