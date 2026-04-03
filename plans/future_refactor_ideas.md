# Future Refactor Ideas

## Move title generation out of message_handler

Title generation currently lives in `_run_turn` in `server/message_handler.py`. It works but isn't the best home for it. The message handler is already doing a lot — managing the turn lifecycle, event buffering, persistence hooks, etc.

A better approach would be to trigger title generation from the persistence layer (`conversations/_store.py`) since that's where the conversation is actually saved. The problem today is that the store is fully synchronous (plain file I/O), so it can't kick off an async LLM call. If the store is ever made async or moved to a database, title generation should move there too.

## Remove fake turn_end from message_handler error path

In `handle_user_message`, the `except` block emits a `TurnEndPayload` when something fails before the turn even starts (e.g. agent build failure, queue setup error). This is misleading — no turn actually started, so there's no turn to end. The frontend should handle the connection erroring out on its own instead of relying on a fake `turn_end` event.
