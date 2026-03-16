# Plan: Improve perform_visual_action — action history, metadata, coordinate scroll

## Context

`perform_visual_action` was implemented in the previous iteration and works end-to-end with the real UI-TARS grounding server. Integration testing (22 tests, all passing) revealed three weaknesses:

1. **No action history** — TARS's system prompt says "you are given a task and your action history" but we only send a single screenshot + task. TARS gets stuck in click-loops (e.g. clicking an input 5 times) because it doesn't know it already clicked. With history, TARS would transition from `click` → `type`.

2. **No action metadata in return** — `perform_visual_action` returns a page snapshot string but doesn't tell the caller what action TARS predicted/executed. The agent can't reason about next steps without knowing what happened.

3. **Scroll ignores TARS coordinates** — TARS returns scroll with a `start_box` position but `execute_action` just does page-level scroll. Should use `mouse.wheel` at TARS's coordinates for element-level scrolling.

## Changes (bottom-up through the pipeline)

### 1. `container/grounding_server.py` — multi-turn message construction

**`_run_inference(image_bytes, task, history=None)`**: Add `history` parameter.

When `history` is a non-empty list of `{"action": str, "screenshot_path": str}` dicts, build multi-turn messages:
```python
messages = [system_prompt]
for entry in history:
    img = Image.open(entry["screenshot_path"])
    messages.append({"role": "assistant", "content": [{"type": "text", "text": entry["action"]}]})
    messages.append({"role": "user", "content": [{"type": "image", "image": img}]})
# Current turn
messages.append({"role": "user", "content": [{"type": "image", "image": current_img}, {"type": "text", "text": task}]})
```
All images (history + current) collected into one list for the processor.

Cap history to last 5 entries to avoid VRAM OOM on the 7B model.

When `history` is None/empty: keep existing single-turn behavior unchanged.

**`_handle_ground`**: Read `history = body.get("history")` from request body, pass to `_run_inference`.

### 2. `container/grounding_client.py` — pass history in request

**`ground_from_path(image_path, task, history=None)`**: When history is not None, include `"history": history` in the JSON body.

**`ground(image_b64, task, history=None)`**: Same for consistency.

### 3. `tools/_grounding.py` — thread history through podman exec

**`GroundingResponse`**: Add field `container_screenshot_path: str = ""` so callers can build history entries referencing container-side paths.

**`run_grounding(..., action_history=None)`**: Add optional parameter.

When `action_history` is not None:
- Write it as JSON to `{host_vision_dir}/_history.json`
- Change the inline script to load history from that file (avoids inlining large data in the script string):
  ```python
  "history = json.load(open(%s)); "
  "result = ground_from_path(%s, %s, history=history); "
  ```
When None: use existing script (no history).

Set `container_screenshot_path` on the returned response.

### 4. `tools/browser/_action_map.py` — coordinate-aware scroll

Replace the scroll branch. When TARS provides coordinates, move mouse there and use `mouse.wheel` instead of `human_scroll`:

```python
elif action == "scroll":
    direction = response.raw.get("scroll_direction", "down")
    if response.x is not None and response.y is not None:
        page_obj = _page_for(frame)
        await page_obj.mouse.move(float(response.x), float(response.y))
        delta_y = {"down": 400, "up": -400}.get(direction, 0)
        delta_x = {"right": 400, "left": -400}.get(direction, 0)
        await page_obj.mouse.wheel(delta_x, delta_y)
    else:
        await human_scroll(frame, direction=direction)
```

### 5. `tools/browser/vision.py` — history accumulation + action summary

**Action history via contextvar:**
```python
_visual_action_history: contextvars.ContextVar[list[dict[str, str]]] = contextvars.ContextVar(
    "_visual_action_history", default=None,
)
```

In `perform_visual_action`:
1. `history = _visual_action_history.get(None) or []`
2. Use unique screenshot filename per step: `"va_%d.png" % len(history)`
3. Pass `action_history=history if history else None` to `run_grounding`
4. After getting response, append `{"action": response.raw.get("action", ""), "screenshot_path": response.container_screenshot_path}` and set the contextvar

**`reset_visual_action_history()`**: Public function to clear history. Export in `__all__`. Agent calls this at start of new tasks.

**Action summary in return value:**

Add `_format_action_summary(response)` that builds a one-liner like:
```
--- Visual action: click at (500, 300) | thought: Found the login button ---
```
Including: action_type, coordinates, typed content, scroll direction, thought.

Prepend this to the page snapshot string in both the action and finished branches.

### 6. `tools/browser/__init__.py` — export `reset_visual_action_history`

### 7. `agents/browser/agent.py` — import reset, call at start if needed

Import `reset_visual_action_history`. No prompt changes needed — the agent already uses `perform_visual_action` correctly.

## Files to modify

| File | Change |
|---|---|
| `container/grounding_server.py` | Multi-turn messages in `_run_inference`, read history in `_handle_ground` |
| `container/grounding_client.py` | Add `history` param to `ground_from_path` and `ground` |
| `tools/_grounding.py` | Add `action_history` param, `container_screenshot_path` field, history JSON file |
| `tools/browser/_action_map.py` | Coordinate-aware scroll with `mouse.wheel` |
| `tools/browser/vision.py` | History contextvar, `_format_action_summary`, `reset_visual_action_history` |
| `tools/browser/__init__.py` | Export `reset_visual_action_history` |
| `agents/browser/agent.py` | Import `reset_visual_action_history` |
| `tests/tools/test_grounding.py` | Test history JSON file, `container_screenshot_path`, backward compat |
| `tests/tools/browser/test_action_map.py` | Coordinate scroll tests, update existing scroll test |
| `tests/tools/browser/test_vision.py` | Test action summary in return, history accumulation, history reset |

## Verification

1. `just test-file tests/tools/test_grounding.py` — history threading + backward compat
2. `just test-file tests/tools/browser/test_action_map.py` — coordinate scroll
3. `just test-file tests/tools/browser/test_vision.py` — summary + history
4. `just test` — full unit suite (719 tests)
5. `just test-integration` on `test_visual_action_integration.py` — real TARS end-to-end
6. Copy updated container files: `podman cp container/grounding_server.py computron_inference:/opt/inference/` and `grounding_client.py`, then kill/restart grounding server before integration tests
