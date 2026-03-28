# AgentEvent Refactor Plan

## Problem

`AgentEvent` is a god-object envelope that overloads two roles:
1. **Content streaming**: `content`, `thinking`, `delta`, `final` fields
2. **Structured event wrapper**: `event: SomePayload` field

These are mutually exclusive at runtime but the model doesn't express that.
Additionally, `final` is overloaded — it means both "this agent is done" and
"close the SSE stream," requiring a filter hack in `message_handler.py`.

## Design

### New payload types

```python
class ContentPayload(BaseModel):
    type: Literal["content"]
    content: str | None = None
    thinking: str | None = None
    delta: bool | None = None

class TurnEndPayload(BaseModel):
    type: Literal["turn_end"]
```

### Flattened union

All payloads (including content and stream-end) join the discriminated union:

```python
AgentEventPayload = Annotated[
    ContentPayload
    | TurnEndPayload
    | ToolCallPayload
    | BrowserScreenshotPayload
    | FileOutputPayload
    | ToolCreatedPayload
    | AudioPlaybackPayload
    | TerminalOutputPayload
    | GenerationPreviewPayload
    | ContextUsagePayload
    | DesktopActivePayload
    | AgentStartedPayload
    | AgentCompletedPayload,
    Field(discriminator="type"),
]
```

### Slim envelope

```python
class AgentEvent(BaseModel):
    payload: AgentEventPayload
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_name: str | None = None
    agent_id: str | None = None
    depth: int | None = None
```

## Removals

- **`final` field** — replaced by `TurnEndPayload` for stream termination.
  `AgentCompletedPayload` already handles agent lifecycle.
- **`AgentEventData` and `data` field** — dead code. No production code
  populates it. Binary content is handled by dedicated payloads
  (`BrowserScreenshotPayload`, `AudioPlaybackPayload`, `FileOutputPayload`).
- **`final` filter in `message_handler.py`** — the root producer emits
  `TurnEndPayload` explicitly; sub-agents never emit it.

## Frontend change

Before:
```js
if (data.event) {
    switch (data.event.type) { ... }
} else {
    // content
}
```

After:
```js
switch (data.payload.type) {
    case 'content': ...
    case 'turn_end': ...
    case 'tool_call': ...
    case 'browser_screenshot': ...
    // ...
}
```

## Migration order

1. Add `ContentPayload`, `TurnEndPayload` to `_models.py`
2. Restructure `AgentEvent`: replace `content`/`thinking`/`delta`/`final`/`data`/`event`
   with single `payload` field
3. Remove `AgentEventData`
4. Update all backend call sites (~20 files)
5. Update `_publish_final()` → emit `AgentEvent(payload=TurnEndPayload(type="turn_end"))`
6. Remove the `final` filter hack in `message_handler.py`
7. Update frontend SSE consumer (`useStreamingChat.js`)
8. Update tests
9. Run `just test` + `just ui-test`
