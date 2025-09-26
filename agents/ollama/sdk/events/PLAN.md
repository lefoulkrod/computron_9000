# Agent Event System Plan

## Requirements
- make events publishable from any point while handling a single user message
- keep the implementation friendly to the asyncio event loop (no blocking, no threads)
- allow the message handler to subscribe and convert events into the streaming wire format consumed by the API/UI
- evolve `UserMessageEvent`, HTTP responses, and the frontend React client so they understand the richer `{content, thinking, data, event}` payload (the UI can initially ignore new fields as long as `content`/`thinking` still arrive)
- model events with an envelope shaped like `{content, thinking, data, event}` where each field is optional, treating `event.type` as a discriminator so new payload kinds slot in cleanly
- support structured metadata for `event`, starting with a `tool_call` type that carries the tool name
- represent binary payloads as `{content_type, content}` where `content` is a base64 string
- cover tool call notifications, model responses, and future custom emitters without rewriting consumers

## Event Schema
```python
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

class AssistantResponseData(BaseModel):
    content_type: str
    content: str  # base64 encoded payload


class ToolCallPayload(BaseModel):
    type: Literal["tool_call"]
    name: str


AssistantEventPayload = Annotated[ToolCallPayload, Field(discriminator="type")]


class AssistantResponse(BaseModel):
    content: str | None = None
    thinking: str | None = None
    data: list[AssistantResponseData] = Field(default_factory=list)
    event: AssistantEventPayload | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

## Implementation Steps
1. [x] Create `agents/ollama/sdk/events/models.py` with the `AssistantResponse`, `ToolCallPayload`, `AssistantResponseData`, and the discriminated `AssistantEventPayload` alias defined above.
2. [x] Add `agents/ollama/sdk/events/context.py` exposing an `asyncio`-native publisher API. Use a `contextvars.ContextVar` to track the active dispatcher so code running inside the message handling coroutine can emit without passing handles around.
3. [x] Implement `agents/ollama/sdk/events/dispatcher.py` that keeps a per-dispatcher subscriber list. Subscribers can be sync or async callables; schedule sync handlers with `loop.call_soon` and async handlers with `asyncio.create_task`. Provide `subscribe`, `unsubscribe`, `publish`, an `asynccontextmanager`-based `subscription` helper that auto-unsubscribes and resets on exit (even after exceptions), plus explicit `reset` utilities.
4. [x] Export the dispatcher helpers and models via `agents/ollama/sdk/events/__init__.py`, and surface a `publish_event` convenience that reads the current dispatcher from the context var before delegating.
5. [x] Introduce a higher-level async context manager in the events package that creates a fresh dispatcher, binds it to the context, and subscribes a provided handler while guaranteeing teardown (unsubscribe + reset) on exit. Leave buffering decisions to callers.
6. [x] Update the message handler to rely on the new context helper but manage its own `asyncio.Queue` (or equivalent) bridge so dispatcher callbacks push events into the queue and the generator drains them in order. As part of this refactor, stop yielding the legacy `(content, thinking)` outputs directly from `run_tool_call_loop`; all outward events should flow through the dispatcher bridge, with any temporary fallback guarded and slated for removal once tool-loop emission lands.
7. [x] Clean up `context.py` by removing redundant helpers (e.g., legacy `bind_dispatcher`) and consolidating exports so the new context manager is the single, obvious binding mechanism.
8. [x] Adjust `UserMessageEvent` (and any other shared models) to expose the richer fields, then update streaming helpers like `server/aiohttp_app.py::stream_events` so the HTTP payload matches the new schema. Phase the rollout so the backend emits the new structure while the frontend React client is enhanced to read it (keeping existing `content`/`thinking` behavior intact while ignoring new keys). add a note for the eventual switch to streaming raw `AssistantResponse` objects (or a thin wrapper) once clients are ready, so the compatibility layer can be retired.
9. [x] Enhance `run_tool_call_loop` directly so it emits `AssistantResponse` instances before invoking a tool (`event=ToolCallPayload(...)`), when the model produces new tokens (`content`/`thinking` fields), and in other strategic locations. Keep the generator contract intact so existing callers keep working while events publish alongside the yields. Ensure events omit tool arguments and stick to the agreed shape, then drop the message-handler fallback once verified.
10. Update the frontend React app to parse the new streaming payload. Continue to display `content` and `thinking` in the existing UI while safely ignoring `data`/`event` until dedicated affordances ship. Coordinate the backend/UI rollout so there is no window where the API emits fields the UI cannot parse.
11. [x] Add tests under `tests/agents/ollama/sdk/events/` (and frontend tests if available) that exercise subscription lifecycles (including the async context manager auto-unsubscribe), mixed sync/async handlers, propagation through the context var, tool-loop emissions, message-handler/HTTP formatting, and API/React integration. Include a regression test that the HTTP layer still returns the expected stream and closes connections cleanly once the loop finishes, a check that no duplicate events reach the client once the fallback is removed, and coverage for the eventual direct `AssistantResponse` streaming path.

    Added:
    - `test_message_handler_bridge.py` verifying only dispatcher-published events surface (no duplicate generator yields).
    - `test_aiohttp_app_assistant_response_stream.py` exercising HTTP streaming with AssistantResponse-shaped objects via a shim and ensuring clean close.
    Existing tests already covered dispatcher lifecycle, model/tool events, and enriched payload shape; UI tests remained green.

## Follow-Ups
- Decide which additional event payload shapes (e.g., tool results, errors) should be introduced and extend the discriminated `AssistantEventPayload` union accordingly.
- Consider exposing a user-facing option to opt-in to raw event streaming versus the current high-level format.
- Explore persistence or replay of events once the in-memory dispatcher behavior is validated.
