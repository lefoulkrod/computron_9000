# Token-Level Streaming for LLM Responses

## Context

Currently both providers (Ollama and Anthropic) wait for the **complete** model response before emitting anything to the frontend. Anthropic even opens a stream but calls `get_final_message()`, discarding all intermediate tokens. The user sees nothing until the entire response is generated, which can take many seconds for long outputs.

The goal is to stream `content` and `thinking` tokens to the frontend as they arrive, so users see text appearing in real-time. The infrastructure is largely ready — the JSONL chunked-HTTP protocol already supports incremental events, and the frontend already appends content from each JSONL line. The main gap is the provider layer and the tool loop.

## How It Works Today

```
Provider.chat() → waits for complete response → ChatResponse
    ↓
_tool_loop.py: publish_event(AssistantResponse(content=FULL_TEXT, thinking=FULL_THINKING))
    ↓
message_handler.py: queue → yield to stream_events()
    ↓
aiohttp: writes one JSONL line with all content at once
    ↓
useStreamingChat.js: appends content to message (but it's the whole thing in one shot)
```

## Streaming Design

```
Provider.chat_stream() → yields ChatDelta tokens → then final ChatResponse
    ↓
_tool_loop.py: for each delta, publish_event(AssistantResponse(content=token, delta=True))
    ↓  (same queue/stream path as today, no changes)
    ↓
useStreamingChat.js: sees delta=true → raw concatenation (no newline heuristic)
```

Key design decisions:
- **New `chat_stream()` method** on providers — `chat()` stays untouched for backward compat
- **`delta` flag** on `AssistantResponse` — tells frontend to raw-concatenate vs. newline-join
- **Tool calls are safe** — both Ollama and Anthropic only emit tool_use blocks at stream end
- **`after_model` hooks** still get the complete `ChatResponse` after streaming finishes

## Implementation

### 1. Add `ChatDelta` model — `sdk/providers/_models.py`

```python
class ChatDelta(BaseModel):
    content: str | None = None
    thinking: str | None = None
```

Export from `sdk/providers/__init__.py`.

### 2. Add `delta` field to `AssistantResponse` — `sdk/events/_models.py`

```python
class AssistantResponse(BaseModel):
    ...
    delta: bool | None = None  # None excluded by exclude_none=True in aiohttp serialization
```

When `delta` is `True`, `content`/`thinking` are incremental tokens to append. When absent (existing behavior), they are complete chunks joined with newlines.

### 3. Add `chat_stream()` to provider protocol — `sdk/providers/_protocol.py`

```python
async def chat_stream(
    self, *, model, messages, tools=None, options=None, think=False,
) -> AsyncGenerator[ChatDelta | ChatResponse, None]:
    ...
```

### 4. Default fallback in `BaseAPIProvider` — `sdk/providers/_base.py`

```python
async def chat_stream(self, **kwargs) -> AsyncGenerator[ChatDelta | ChatResponse, None]:
    # Fallback: call chat() and yield the complete response (no token streaming)
    yield await self.chat(**kwargs)
```

This means OpenAI stub and any future providers work without changes.

### 5. Implement `chat_stream()` in Ollama — `sdk/providers/_ollama.py`

- Call `self._client.chat(**kwargs, stream=True)` → returns async iterator of chunks
- Each chunk has `message.content` and `message.thinking` token fragments
- Yield `ChatDelta(content=chunk_content, thinking=chunk_thinking)` for each
- Accumulate full content/thinking/tool_calls across chunks
- After stream ends, yield final `ChatResponse` (using `_normalize_response` on accumulated data)
- Tool calls arrive only in the final chunk (`done=True`), so streaming is safe

### 6. Implement `chat_stream()` in Anthropic — `sdk/providers/_anthropic.py`

- Use `self._client.messages.stream(**kwargs)` (already used today!)
- Instead of `await stream.get_final_message()`, iterate the stream events:
  - `content_block_delta` with `type="text_delta"` → yield `ChatDelta(content=delta.text)`
  - `content_block_delta` with `type="thinking_delta"` → yield `ChatDelta(thinking=delta.thinking)`
- After iteration, call `await stream.get_final_message()` for the complete response with tool calls
- Yield final `ChatResponse` via existing `_normalize_response()`

### 7. Add `_stream_chat_with_retries()` — `sdk/loop/_tool_loop.py`

Mirrors `_chat_with_retries()` but uses `chat_stream()`:

```python
async def _stream_chat_with_retries(provider, *, agent, messages, tools=None, retries=5):
    """Yield ChatDelta tokens, then the final ChatResponse. Retries on failure."""
    resolved_tools = tools if tools is not None else (agent.tools or [])
    attempt = 0
    total_attempts = 1 + max(0, retries)
    while attempt < total_attempts:
        try:
            async for chunk in provider.chat_stream(
                model=agent.model, messages=messages,
                options=agent.options, tools=resolved_tools, think=agent.think,
            ):
                yield chunk
            return  # stream completed successfully
        except ProviderError as exc:
            attempt += 1
            if not exc.retryable or attempt >= total_attempts:
                raise
            logger.warning("chat_stream failed (attempt %s/%s): %s", attempt, total_attempts, exc)
```

**Retry safety:** If a stream fails mid-way after emitting deltas, the partial text is already on screen. On retry, new deltas append to it. This could cause duplication. Mitigation: if `attempt > 0` (retrying), fall back to `provider.chat()` (non-streaming) and yield the result as a single `ChatResponse`. The tool loop emits a non-delta event with complete content, and the frontend's existing newline-join logic handles it as a replacement of the last segment.

### 8. Modify `run_tool_call_loop()` — `sdk/loop/_tool_loop.py`

Replace the `_chat_with_retries` call (line 208) with streaming:

```python
# Stream deltas to frontend as tokens arrive
response: ChatResponse | None = None
async for chunk in _stream_chat_with_retries(provider, agent=agent, messages=messages, tools=tools):
    if isinstance(chunk, ChatDelta):
        publish_event(AssistantResponse(
            content=chunk.content,
            thinking=chunk.thinking,
            delta=True,
        ))
    elif isinstance(chunk, ChatResponse):
        response = chunk

# after_model hooks get the complete response (unchanged)
for hook in hooks:
    fn = getattr(hook, "after_model", None)
    if fn:
        response = await fn(response, history, iteration, agent.name)

content = response.message.content
thinking = response.message.thinking
tool_calls = response.message.tool_calls

# Skip the old full-content publish_event — deltas already sent
# (Only publish if after_model hooks rewrote the content)
# ... rest of existing code unchanged (history append, tool execution)
```

The existing `publish_event(AssistantResponse(content=content, thinking=thinking))` on line 238 becomes conditional: only emit it if no deltas were streamed (fallback path) or if `after_model` hooks modified the content.

### 9. Frontend delta handling — `server/ui/src/hooks/useStreamingChat.js`

Modify the content-append logic (lines 294-306):

```javascript
if (hasResponse) {
    const existingContent = next.content || '';
    if (data.delta) {
        // Token delta: raw concatenation, no newline insertion
        next.content = existingContent + contentField;
    } else {
        // Complete chunk (legacy / after-hook rewrite): existing newline-join logic
        let toAppend = contentField;
        if (existingContent) {
            const endsWithNewline = /\n\s*$/.test(existingContent);
            const startsWithBlock = /^\s*(?:```|\n)/.test(toAppend);
            if (!endsWithNewline && !startsWithBlock) {
                toAppend = '\n' + toAppend;
            }
        }
        next.content = existingContent + toAppend;
    }
    currentHasResponse = true;
}
```

Same pattern for thinking (lines 282-292): when `data.delta`, raw concatenation.

**No other frontend changes needed.** The `streaming` flag, `final` handling, message segmentation, depth/agent_name tracking all remain the same.

### 10. Streaming markdown rendering — `server/ui/src/components/Message.jsx`

Install `remend` (`npm install remend`) — a preprocessor that auto-closes unclosed markdown constructs (fenced code blocks, `**`, `$$`, `[](`, etc.) so react-markdown always receives valid syntax during streaming.

Add `streaming` prop to `MarkdownContent` and pipe content through `remend` when active:

```javascript
import remend from 'remend';

function MarkdownContent({ children, streaming }) {
    let content = preprocessContent(children || '');
    if (streaming) content = remend(content);
    return (
        <ReactMarkdown
            urlTransform={_urlTransform}
            remarkPlugins={[remarkMath, remarkGfm, remarkBreaks]}
            rehypePlugins={[[rehypeKatex, { strict: 'ignore' }], [rehypeSanitize, sanitizeSchema]]}
            components={markdownComponents}
        >
            {content}
        </ReactMarkdown>
    );
}
```

Wire `streaming` from `AssistantMessage` (the message object already carries it via `useStreamingChat.js`):

```jsx
function AssistantMessage({ content, thinking, images, placeholder, agent_name,
                            depth = 0, data, contextUsage, onPreview, streaming }) {
    // ...
    {!placeholder && <MarkdownContent streaming={streaming}>{content}</MarkdownContent>}
```

**Why `remend` instead of a full renderer swap:** `streamdown` (Vercel's streaming markdown component that uses `remend` internally) requires Tailwind CSS. Our project uses CSS Modules, so `remend` as a standalone preprocessor is the right fit — zero styling opinions, keeps all existing plugins and custom components.

**Future performance optimization:** If long responses with many code blocks cause re-render jank, we can adopt streamdown's block-memoization pattern (split markdown into blocks at stable boundaries, wrap each in `React.memo`, only re-render the active block). Their source is at `github.com/vercel/streamdown` for reference.

## Files

| Action | File |
|--------|------|
| Modify | `sdk/providers/_models.py` — add `ChatDelta` model |
| Modify | `sdk/providers/__init__.py` — export `ChatDelta` |
| Modify | `sdk/providers/_protocol.py` — add `chat_stream()` to protocol |
| Modify | `sdk/providers/_base.py` — add default `chat_stream()` fallback |
| Modify | `sdk/providers/_ollama.py` — implement `chat_stream()` |
| Modify | `sdk/providers/_anthropic.py` — implement `chat_stream()` |
| Modify | `sdk/events/_models.py` — add `delta` field to `AssistantResponse` |
| Modify | `sdk/loop/_tool_loop.py` — add `_stream_chat_with_retries()`, modify `run_tool_call_loop()` |
| Modify | `server/ui/src/hooks/useStreamingChat.js` — delta-aware content append |
| Modify | `server/ui/src/components/Message.jsx` — `remend` preprocessing during streaming |
| Add dep | `server/ui/package.json` — add `remend` |

## Risk Mitigation

1. **Backward compat**: `delta` defaults to `None`, excluded from JSON via `exclude_none=True`. Old frontend code never sees it. `chat()` method unchanged.
2. **Tool call safety**: Tool calls only appear in the final `ChatResponse`. Tool execution happens after stream completes.
3. **Hook compat**: `before_model`/`after_model` hooks run before/after the stream, not per-token. No changes needed.
4. **Retry safety**: Retries after partial streaming fall back to non-streaming `chat()` to avoid content duplication.
5. **Sub-agent depth**: Delta events pass through `publish_event()` which enriches with `agent_name`/`depth` from context stack. No changes needed.
6. **Message handler filtering**: Deltas are not `final`, so they pass through the depth filter in `message_handler.py` correctly.
7. **Streaming markdown**: `remend` heals incomplete syntax before react-markdown sees it, preventing code block/math block rendering artifacts.

## Verification

1. `just test` — all existing tests pass (no behavioral changes to `chat()`)
2. Write unit tests for `chat_stream()` on both providers
3. Write unit test for `_stream_chat_with_retries()`
4. Manual test: send a message, verify tokens appear incrementally in the UI
5. Manual test: trigger a tool call (e.g. browse), verify tool execution still works after streaming
6. Manual test: verify `after_model` hooks still work (e.g. context_usage events)
7. Manual test: verify markdown renders cleanly during streaming (code blocks, math, bold, links)
8. `just ui-build` — frontend builds cleanly
