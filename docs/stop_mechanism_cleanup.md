# Stop Mechanism Cleanup & Extraction Loop Fix

## Context

Three user-reported issues:
1. Skills extraction runs concurrently with active agent work — the `is_turn_active()` guard checks for `"default"` session but real sessions use UUIDs, so it never fires
2. Stop request doesn't take effect promptly — no `check_stop()` between tool calls in a batch
3. Dead code in stop hook; agents don't get a wrap-up message on stop

## Changes

### 1. Add `check_stop()` between tool calls — `sdk/loop/_tool_loop.py`

Add `check_stop` to the import from `._turn` (line 15). Insert `check_stop()` at the top of the `for tool_call in tool_calls:` loop body (after line 250), before `tool_name = ...`. The existing `except StopRequestedError` at line 281 catches it.

### 2. Wrap-up model call on stop — `sdk/loop/_tool_loop.py`

Replace the `except StopRequestedError` handler (lines 281-284) with a wrap-up flow:

```python
except StopRequestedError:
    logger.info("Agent '%s' tool loop stopped by user request", agent.name)
    history.append({
        "role": "user",
        "content": "The user has requested to stop. Wrap up your response.",
    })
    try:
        response = await _chat_with_retries(
            provider, agent=agent, messages=history.messages, tools=[],
        )
        content = response.message.content
        if content:
            history.append({"role": "assistant", "content": content})
            yield content, response.message.thinking
    except Exception:
        logger.exception("Error during stop wrap-up for agent '%s'", agent.name)
    _publish_final()
    return
```

This calls `_chat_with_retries` directly (bypasses hooks — no re-triggering `check_stop`), passes `tools=[]` so the model can't make more tool calls, and yields the wrap-up content. For sub-agents, this becomes the tool result the parent receives.

### 3. Simplify `StopHook.after_model` — `sdk/hooks/_stop_hook.py`

The wrap-up logic is now in the loop's except handler. Simplify `after_model` to just `check_stop(); return response` — same as `before_model` but returns the response.

### 4. Remove dead `except StopRequestedError` — `sdk/tools/_agent_wrapper.py`

`_run_tool_loop_once` (line 193) has `except StopRequestedError: raise` that can never fire — the generator catches it internally. Remove the dead except block and the now-unused `StopRequestedError` import.

### 5. Remove dead `except StopRequestedError` — `agents/sub_agent/agent.py`

Same as #4. `run_sub_agent` (line 151) has an unreachable `except StopRequestedError: raise`. Remove it and the unused import.

### 6. Extraction loop re-checks between conversations — `skills/_extractor.py`

Add `if any_turn_active(): break` at the top of the `for summary in unanalyzed:` loop body (after line 725). `break` not `continue` — once a turn is active, skip remaining conversations this cycle. They'll be retried next cycle.

(`any_turn_active()` in `_turn.py`/`__init__.py` and the top-of-cycle check are already applied from in-progress work.)

### 7. Tests

- **`tests/sdk/test_turn.py`**: Add tests for `any_turn_active()` (false when idle, true during turn_scope)
- **`tests/sdk/test_tool_loop_stop.py`** (new): Two tests:
  1. `check_stop()` fires between tool calls — model returns 3 tool calls, first tool sets stop event, assert only first tool executed
  2. Wrap-up model call happens — after stop, verify the provider gets one more call (with no tools) and the wrap-up content is yielded

## Files to modify

| File | Change |
|------|--------|
| `sdk/loop/_tool_loop.py` | Import `check_stop`; add between tool calls; wrap-up in except handler |
| `sdk/hooks/_stop_hook.py` | Simplify `after_model` to just `check_stop()` |
| `sdk/tools/_agent_wrapper.py` | Remove dead except block + unused import |
| `agents/sub_agent/agent.py` | Remove dead except block + unused import |
| `skills/_extractor.py` | Add `any_turn_active()` check inside conversation loop |
| `tests/sdk/test_turn.py` | Add `any_turn_active` tests |
| `tests/sdk/test_tool_loop_stop.py` (new) | Test stop between tools + wrap-up call |

## Verification

1. `just test-file tests/sdk/test_turn.py`
2. `just test-file tests/sdk/test_tool_loop_stop.py`
3. `just test-file tests/sdk/test_tool_loop_serialization.py`
4. `just test-unit`

## In-progress edits (already applied, not yet committed)

- `sdk/loop/_turn.py`: `any_turn_active()` added
- `sdk/loop/__init__.py`: `any_turn_active` exported
- `skills/_extractor.py`: top-of-cycle check changed from `is_turn_active()` to `any_turn_active()`
