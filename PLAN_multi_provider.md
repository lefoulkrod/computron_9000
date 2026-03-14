# Multi-Provider LLM Support

## Context

The project hard-codes `ollama.AsyncClient` in 5 files (6 call sites). The goal is to introduce a `Provider` Protocol so the system can run on Ollama, OpenAI, or Anthropic — selected globally in config. The provider package lives at `sdk/providers/`. No if/else branching in consumer code; providers are pluggable via Protocol + registry.

Recent refactoring moved `agents/ollama/sdk/` → `sdk/` and `agents/ollama/message_handler.py` → `server/message_handler.py`. The old `PLAN_multi_provider.md` has stale paths.

---

## Phase 1: Provider types and protocol

**New files:**
- `sdk/providers/__init__.py` — `get_provider()`, `reset_provider()`, re-exports
- `sdk/providers/_protocol.py` — `Provider` Protocol
- `sdk/providers/_models.py` — `ChatResponse`, `ChatMessage`, `ToolCall`, `ToolCallFunction`, `TokenUsage`, `GenerateResponse`

### Provider Protocol (`sdk/providers/_protocol.py`)

```python
class Provider(Protocol):
    @classmethod
    def from_config(cls, llm_config: LLMConfig) -> Provider: ...

    async def chat(
        self, *, model: str, messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None = None,
        options: dict[str, Any] | None = None, think: bool = False,
    ) -> ChatResponse: ...

    async def generate(
        self, *, model: str, prompt: str, system: str | None = None,
        options: dict[str, Any] | None = None, think: bool = False,
    ) -> GenerateResponse: ...

    async def list_models(self) -> list[str]: ...
```

### Normalized response types (`sdk/providers/_models.py`)

Designed to be the superset of Ollama, OpenAI, and Anthropic response shapes. Each
provider normalizes its native types into these. Consumer code never touches
provider-specific types.

**Native type mapping reference:**

| Our type | Ollama native | OpenAI native | Anthropic native |
|----------|--------------|---------------|-----------------|
| `ChatMessage` | `Message` | `ChatCompletionMessage` | `Message.content[]` blocks |
| `ChatResponse` | `ChatResponse` | `ChatCompletion` | `Message` |
| `ToolCall` | `Message.ToolCall` | `ChatCompletionMessageToolCall` | `ToolUseBlock` |
| `GenerateResponse` | `GenerateResponse` | N/A (use chat) | N/A (use chat) |
| token fields | `prompt_eval_count`/`eval_count` | `usage.prompt_tokens`/`completion_tokens` | `usage.input_tokens`/`output_tokens` |

**Model definitions:**

```python
class ToolCallFunction(BaseModel):
    """Normalized function within a tool call."""
    name: str
    arguments: dict[str, Any]
    # Ollama: already a dict
    # OpenAI: provider must json.loads() the string
    # Anthropic: maps from ToolUseBlock.input (already a dict)


class ToolCall(BaseModel):
    """A single tool invocation requested by the model."""
    id: str | None = None  # OpenAI/Anthropic provide IDs, Ollama does not
    function: ToolCallFunction
    # Ollama: maps from Message.ToolCall.function
    # OpenAI: maps from ChatCompletionMessageToolCall.function
    # Anthropic: maps from ToolUseBlock (name→function.name, input→function.arguments)


class ChatMessage(BaseModel):
    """Provider-agnostic assistant message from a chat completion."""
    content: str | None = None
    thinking: str | None = None
    tool_calls: list[ToolCall] | None = None
    # Ollama: direct mapping from Message fields
    # OpenAI: content from .content, thinking=None, tool_calls from .tool_calls
    # Anthropic: iterate .content blocks — TextBlock→content, ThinkingBlock→thinking,
    #            ToolUseBlock→tool_calls


class TokenUsage(BaseModel):
    """Normalized token counts."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Ollama: prompt_eval_count, eval_count
    # OpenAI: usage.prompt_tokens, usage.completion_tokens
    # Anthropic: usage.input_tokens, usage.output_tokens


class ChatResponse(BaseModel):
    """Normalized response from any provider's chat endpoint."""
    message: ChatMessage
    usage: TokenUsage = Field(default_factory=TokenUsage)
    done_reason: str | None = None
    raw: Any = None  # Original provider response for provider-specific stats
    # Ollama: done_reason from .done_reason
    # OpenAI: done_reason from .choices[0].finish_reason
    # Anthropic: done_reason from .stop_reason

    class Config:
        arbitrary_types_allowed = True


class GenerateResponse(BaseModel):
    """Normalized response from a text generation request."""
    text: str
    thinking: str | None = None
    raw: Any = None

    class Config:
        arbitrary_types_allowed = True
```

**Design decisions:**
- `ChatMessage` not `LLMMessage` — mirrors the "chat completion" concept all 3 providers share
- `ChatResponse` not `LLMResponse` — same reasoning; `GenerateResponse` covers the non-chat path
- `ToolCall.id` is optional — Ollama doesn't provide one, OpenAI/Anthropic do (needed for tool result correlation)
- `TokenUsage` is a proper model, not bare ints — matches the structure all 3 providers use and is reusable by `TokenTracker`
- `done_reason` captured for hook logic that may need to know why generation stopped
- `GenerateResponse.text` not `.response` — clearer name, avoids confusion with the parent response object
- `raw` on both response types — allows `LoggingHook` to extract Ollama-specific timing stats without coupling the model to Ollama

### Provider registry (`sdk/providers/__init__.py`)

Lazy import via dotted-path registry — no if/else:

```python
_PROVIDER_PATHS: dict[str, str] = {
    "ollama": "sdk.providers._ollama:OllamaProvider",
    "openai": "sdk.providers._openai:OpenAIProvider",
    "anthropic": "sdk.providers._anthropic:AnthropicProvider",
}
```

`get_provider()` reads `cfg.llm.provider`, looks up the path, does `importlib.import_module`, calls `cls.from_config(cfg.llm)`. Caches the singleton. `reset_provider()` for testing.

---

## Phase 2: Ollama provider implementation

**New file:** `sdk/providers/_ollama.py`

- `OllamaProvider.__init__(host: str | None)`
- `from_config(llm_config)` reads `llm_config.host`
- `chat()` — wraps existing `ollama.AsyncClient.chat()` call, normalizes `ChatResponse` → `ChatResponse`
  - Maps `prompt_eval_count` → `prompt_tokens`, `eval_count` → `completion_tokens`
  - Maps `response.message.tool_calls` → `list[ToolCall]`
  - Stores raw response in `ChatResponse.raw`
- `generate()` — wraps `client.generate()`, returns `GenerateResponse`
- `list_models()` — wraps `client.list()`

---

## Phase 3: Config changes

**File:** `config/__init__.py`

Add to `LLMConfig`:
```python
provider: str = "ollama"
api_key: str | None = None   # or from LLM_API_KEY env var
base_url: str | None = None  # for OpenAI-compatible endpoints
```

No changes to `ModelConfig` — the `model` field is just a string identifier that works for any provider (e.g. `gpt-4o`, `claude-sonnet-4-20250514`).

**File:** `config.yaml` — add `provider: ollama` under `llm:` section.

---

## Phase 4: Rename `to_ollama_options()` → `to_options()`

**File:** `agents/types.py` — rename method, same implementation.

**3 call sites to update:**
- `server/message_handler.py:190`
- `sdk/run_agent_tools.py:310`
- `agents/sub_agent/agent.py:91`

---

## Phase 5: Swap all ollama.AsyncClient call sites

### 5a. `sdk/tool_loop.py` (primary coupling)

- Remove `from ollama import AsyncClient, ChatResponse`
- Import `from sdk.providers import get_provider` and `ChatResponse`
- `run_tool_call_loop()`: replace `AsyncClient(host=...)` with `get_provider()`
- `_chat_with_retries()`: change first param from `client: AsyncClient` to `provider: Provider`, call `provider.chat(...)` instead of `client.chat(...)`, return `ChatResponse` instead of `ChatResponse`
- Response field access (`response.message.content`, `.thinking`, `.tool_calls`) works unchanged — our normalized types use the same field names

### 5b. `sdk/context/_strategy.py`

- Remove `from ollama import AsyncClient`
- In `_call_summarizer()`: replace `AsyncClient(host=...)` + `client.chat(...)` with `get_provider().chat(...)`
- Drop `stream=False` param (not part of Provider protocol)
- Return `response.message.content or ""`— unchanged

### 5c. `models/generate_completion.py`

- Remove `from ollama import AsyncClient`
- Replace with `get_provider().generate(...)`
- Return `(response.text, response.thinking)` — matches `GenerateResponse` fields

### 5d. `server/aiohttp_app.py`

- Remove `from ollama import AsyncClient`
- Replace `client.list()` with `get_provider().list_models()`

---

## Phase 6: Token counter update

**File:** `sdk/context/_token_tracker.py`

Replace `OllamaTokenCounter` with `_ChatResponseTokenCounter` that reads from `ChatResponse.usage`:

```python
class _ChatResponseTokenCounter:
    def extract_usage(self, response: Any) -> TokenUsage:
        usage = getattr(response, "usage", None)
        if usage is None:
            return TokenUsage()
        return TokenUsage(
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
```

Note: `TokenUsage` from `sdk/providers/_models` and `TokenUsage` from `sdk/context/_models` are currently separate types with the same fields. Keep both — the context one is internal to context management, the providers one is the normalized API surface. The counter bridges them.

**File:** `sdk/context/_manager.py` — update default counter from `OllamaTokenCounter()` to `_ChatResponseTokenCounter()`.

---

## Phase 7: Runtime stats

**File:** `sdk/llm_runtime_stats.py`

- Change type annotation from `ChatResponse | GenerateResponse` to `Any`
- Remove `from ollama import ChatResponse, GenerateResponse`
- The function body already uses `getattr` throughout, so it works with any response object
- When the provider is Ollama, `ChatResponse.raw` contains the original `ChatResponse` with timing data

**File:** `sdk/hooks/_logging_hook.py`

- In `after_model()`, the stats check `hasattr(response, "done")` — this won't match `ChatResponse`
- Change to check `response.raw` for Ollama-specific stats: `if hasattr(getattr(response, 'raw', None), 'done')`
- Pass `response.raw` to `llm_runtime_stats()` instead of `response`

---

## Phase 8: Stub providers

**New files:**
- `sdk/providers/_openai.py` — `OpenAIProvider` stub (raises `NotImplementedError`)
- `sdk/providers/_anthropic.py` — `AnthropicProvider` stub (raises `NotImplementedError`)
- `sdk/providers/_tool_schema.py` — `callable_to_json_schema()` utility for OpenAI/Anthropic (needed when those providers are implemented)

---

## Phase 9: Tests

**New test files:**
- `tests/sdk/providers/__init__.py`
- `tests/sdk/providers/test_models.py` — round-trip serialization of response types
- `tests/sdk/providers/test_ollama.py` — mock `ollama.AsyncClient`, verify normalization
- `tests/sdk/providers/test_provider_factory.py` — verify `get_provider()` registry lookup

**Existing tests to update:**
- Any test that mocks `ollama.AsyncClient` in `sdk/tool_loop` or `sdk/context/_strategy` needs to mock `get_provider()` instead
- `tests/sdk/context/test_strategy.py` — mock provider instead of AsyncClient
- `tests/sdk/test_tool_loop_serialization.py` — mock provider
- `tests/sdk/hooks/test_context_hook.py` — if it checks response attributes, use `ChatResponse`

---

## Files summary

| New file | Purpose |
|----------|---------|
| `sdk/providers/__init__.py` | `get_provider()`, registry, re-exports |
| `sdk/providers/_protocol.py` | `Provider` Protocol |
| `sdk/providers/_models.py` | `ChatResponse`, `ChatMessage`, `ToolCall`, `TokenUsage`, `GenerateResponse` |
| `sdk/providers/_ollama.py` | Ollama implementation |
| `sdk/providers/_openai.py` | OpenAI stub |
| `sdk/providers/_anthropic.py` | Anthropic stub |
| `sdk/providers/_tool_schema.py` | Callable → JSON schema utility |

| Modified file | Change |
|----------------|--------|
| `config/__init__.py` | Add `provider`, `api_key`, `base_url` to `LLMConfig` |
| `config.yaml` | Add `provider: ollama` |
| `agents/types.py` | Rename `to_ollama_options()` → `to_options()` |
| `server/message_handler.py` | Call `to_options()` |
| `sdk/run_agent_tools.py` | Call `to_options()` |
| `agents/sub_agent/agent.py` | Call `to_options()` |
| `sdk/tool_loop.py` | Use `get_provider()` instead of `AsyncClient` |
| `sdk/context/_strategy.py` | Use `get_provider()` instead of `AsyncClient` |
| `sdk/context/_token_tracker.py` | Replace `OllamaTokenCounter` with `_ChatResponseTokenCounter` |
| `sdk/context/_manager.py` | Use new default token counter |
| `models/generate_completion.py` | Use `get_provider()` instead of `AsyncClient` |
| `server/aiohttp_app.py` | Use `get_provider().list_models()` |
| `sdk/llm_runtime_stats.py` | Accept `Any`, drop ollama imports |
| `sdk/hooks/_logging_hook.py` | Access `response.raw` for stats |

---

## Verification

1. `just test` — all 553 existing tests pass
2. New unit tests for provider models, ollama normalization, factory
3. `just run` — manual smoke test: send a message, verify tool calling works end-to-end
