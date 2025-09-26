# Agent Event Sub-Context Plan

## Goals
- Allow any agent executed inside another agent (e.g., via `run_agent_as_tool_function`) to run in its own "sub-context".
- Propagate a structural context identifier with every dispatched event so subscribers can choose which context(s) to consume.
- Keep `AssistantResponse` unchanged; context metadata lives in the dispatcher layer.
- Require subscribers to opt into the richer envelope (no compatibility shim).

## Design Overview
1. Maintain a stack of context identifiers alongside the dispatcher using a `ContextVar`. The top-level agent pushes a root id (e.g., `"root"`); each nested agent tool pushes a child id derived from the parent.
2. Wrap emissions in a new `DispatchEvent` dataclass containing:
   - `context_id`: current context id (string)
   - `parent_context_id`: id of the immediate parent (string | None)
   - `depth`: root = 0, child increments depth
   - `payload`: the original `AssistantResponse`
3. Adjust subscription helpers (`subscribe`, `subscription`, `event_context`) so handlers now receive the full `DispatchEvent` envelope instead of a bare `AssistantResponse`.
4. Generate deterministic child ids in `make_run_agent_as_tool_function` (e.g., `{parent}.{agent_name}.{counter}`) and push/pop them via a helper context manager before calling `run_tool_call_loop`.
5. Update `run_tool_call_loop` and other event publishers to hand `AssistantResponse` to `publish_event`; the dispatcher wraps it with the current context metadata on the way out.
6. Adjust `handle_user_message` (and any other subscribers) to consume `DispatchEvent` objects and gate on `depth == 0` by default so the UI only streams top-level content while still exposing nested events if desired.

## Implementation Steps
1. **Context Management**
   - Introduce a `ContextVar[list[str]]` holding the current context stack.
   - Add helpers: `push_context_id(id: str)`, `pop_context_id()`, `current_context_id()`, `current_depth()`.
2. **Dispatcher Envelope**
   - Define `DispatchEvent` dataclass in `agents/ollama/sdk/events/models.py` (or new module) with the fields above.
   - Replace the dispatcher handler type with `Callable[[DispatchEvent], Awaitable[None] | None]`.
   - Update `publish_event` to build a `DispatchEvent` before invoking subscribers.
3. **Subscription API**
   - Update `EventDispatcher.subscribe`/`unsubscribe`/`publish` to work with the new handler signature.
   - Extend `subscription` and `event_context` helpers to accept optional `context_filter: Callable[[DispatchEvent], bool]`.
4. **Agent Tool Integration**
   - Enhance `make_run_agent_as_tool_function` so the generated wrapper pushes a child context id before invoking `_run_tool_loop_once`/`run_tool_call_loop` and pops it afterward.
   - Ensure nested agent tools compose ids by basing the child id on the parent id plus agent name and a local counter.
5. **Message Handler**
   - Update `handle_user_message` queue bridge to store `DispatchEvent` objects (instead of raw `AssistantResponse`). Filter on `event.depth == 0` for UI streaming but keep all events queued for future observers if needed.
6. **Server Stream**
   - Adjust `server/aiohttp_app.py::stream_events` to read from the new event structure (e.g., `event.payload.content`, `event.context_id`).
7. **Cleanup**
   - Remove any unused compatibility helpers (e.g., legacy `UserMessageEvent` fields) once the new envelope is wired through.

## Testing
- Unit tests for dispatcher ensuring context stack push/pop works, events carry correct ids, and filters behave as expected.
- Unit tests for `run_agent_as_tool_function` verifying nested calls produce unique, hierarchical context ids.
- Unit tests for `handle_user_message` confirming only depth-0 events reach the UI queue while nested events remain accessible to other subscribers.
- Integration test for the aiohttp stream asserting context metadata is present and correctly scoped for nested agent tool calls.

## Follow-Ups
- Decide on a naming scheme for context ids (e.g., UUID vs. hierarchical string) and document it for subscribers.
- Explore exposing context metadata to the UI if future designs want to surface nested agent activity.
