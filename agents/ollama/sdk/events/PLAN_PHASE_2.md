# Agent Event System – Phase 2 Follow-Ups

## Backend TODOs
- Emit a terminal `AssistantResponse` with `final=True` (or equivalent flag) when `run_tool_call_loop` finishes so consumers can detect completion without relying on EOF.
- Rework `_handle_image_message` to publish `AssistantResponse` objects through the dispatcher (and reuse the queue bridge) so vision flows honor content suppression/settings identical to the text path.
- Once the final event path exists, simplify `handle_user_message` by removing the sentinel queue plumbing and any legacy fallbacks.
- After the UI migration (see below), drop legacy serialization branches (`response`, `message` duplication) from `UserMessageEvent`, `stream_events`, and related types.

## Frontend & API Alignment
- Update `server/ui/src/App.jsx` (and related components) to consume `content`, `thinking`, `data`, and `event` directly, falling back to legacy fields only until the backend cleanup lands.
- When the React UI is updated, remove the legacy `response`/`thinking` compatibility path entirely (types, serialization, tests).

## Testing & Verification
- Add targeted unit tests covering:
  * final-event emission and ordering of streamed responses;
  * content suppression behaviour when agent tools run inside `run_tool_call_loop` (including nested agent-as-tool invocations);
  * `_handle_image_message` dispatcher integration once implemented.
- Add integration coverage:
  * aiohttp streaming end-to-end test that asserts the enriched payload and final event;
  * UI/integration test (or storybook fixture) that exercises the new fields.

## Cleanup
- Remove temporary helpers / TODOs introduced for the transition (e.g., sentinel queue handling) once final-event flow is stable.
- Audit for any remaining references to `UserMessageEvent.message` / `response` legacy fields and delete them after frontend migration.
- Document the agent-tool marker (`__agent_as_tool_marker__`) and consider replacing it with a typed wrapper if future use-cases need richer metadata.

