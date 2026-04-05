# Future Refactor Ideas

## Move title generation out of message_handler

Title generation currently lives in `_run_turn` in `server/message_handler.py`. It works but isn't the best home for it. The message handler is already doing a lot — managing the turn lifecycle, event buffering, persistence hooks, etc.

A better approach would be to trigger title generation from the persistence layer (`conversations/_store.py`) since that's where the conversation is actually saved. The problem today is that the store is fully synchronous (plain file I/O), so it can't kick off an async LLM call. If the store is ever made async or moved to a database, title generation should move there too.

## Generate proper icon components for Sidebar

The icons in `server/ui/src/components/Sidebar.jsx` are defined as raw SVG path strings inline in the `PANELS` array. This makes them difficult to read, edit, and maintain — you can't tell what an icon looks like without rendering it.

Since we generate our own icons, we should generate proper icon components for each sidebar panel so each entry references a readable component name instead of opaque path data. This would also make it easier to add new panels or swap icons later.

## Remove fake turn_end from message_handler error path

In `handle_user_message`, the `except` block emits a `TurnEndPayload` when something fails before the turn even starts (e.g. agent build failure, queue setup error). This is misleading — no turn actually started, so there's no turn to end. The frontend should handle the connection erroring out on its own instead of relying on a fake `turn_end` event.

## Unify agent spawning

Currently root agents (message_handler), sub-agents (spawn_agent), and background tasks (TaskExecutor) each duplicate agent setup logic — system message construction, context manager creation, hook assembly, skill/tool management, persistence. Each new caller re-implements the same pattern with slight variations.

**Goal:** Extract a shared `run_agent_turn()` that handles all common setup. Callers only differ in how they provide the conversation:
- message_handler: reuses existing ConversationHistory, persists to main history.json
- spawn_agent: fresh ConversationHistory, persists to sub_agents/ dir
- TaskExecutor: fresh ConversationHistory, persists to goals/ dir
- Future wrappers (Telegram bot, CLI): same shared function, different conversation source

**What moves into the shared path:**
- System message construction (base prompt + memory + skill prompts)
- Hook assembly (default_hooks + PersistenceHook)
- ContextManager creation
- LoadedSkills creation and skill pre-loading
- agent_span lifecycle

## Revisit default_hooks assembly

`default_hooks()` in `sdk/hooks/_default.py` builds the hook list via a series of conditionals that check agent options, `max_iterations`, and whether a `ctx_manager` was provided. Every caller gets the same monolithic list with no way to opt out of individual hooks or inject custom ones without bypassing the function entirely.

This makes it hard to customize hook sets for different agent types — for example, a sub-agent might not need `ScratchpadHook` or `LoadedSkillHook`, but there's no way to express that without duplicating the whole assembly. The function also takes `agent: Any` and reaches into `agent.options` directly, coupling it to the agent's internal shape.

A better approach might be a declarative hook configuration (e.g. a list of hook classes/names on the agent definition) or a builder pattern that lets callers include/exclude specific hooks. This would also make it easier to test individual hooks in isolation without standing up the full default set.

## Remove strongly-typed agent result machinery

`_agent_wrapper.py` has a `result_type` parameter and a bunch of supporting code to coerce agent text output into typed Python values (Pydantic models, `list[Model]`, builtins, etc.). This includes `_convert_result_to_type`, `_run_with_json_retry`, `_validate_pydantic_model`, `AgentToolConversionError`, and the `_PydanticV2`/`_PydanticV1` protocols. The `make_run_agent_as_tool_function` factory branches on `result_type is str` vs non-string and retries the entire tool loop up to 5 times on JSON parse failures.

None of this is actually used — all agent tools return `str`. The typed-result path adds complexity (generic type vars, Pydantic protocol sniffing, retry loops) for a feature that never materialized. Remove `result_type` from the factory signature, delete the conversion/retry helpers and the custom exception, and simplify the factory to always return `str`. Also clean up any related test code.

## Eliminate integration tests

Server tests (tests/server/) trigger real Ollama HTTP calls during `create_app()` import/startup, even though test logic uses monkeypatched fakes. All tests should run without external services. Audit the app startup path to eliminate the Ollama call.

## Add streaming progress to grounding tool

`tools/_grounding.py` uses a blocking `subprocess.run()` with a 31-minute timeout. When the UI-TARS model (~33 GB) downloads for the first time, the UI goes silent with no progress. Image and music generation both stream JSONL progress events. The grounding tool should do the same.

## Simplify inference client/server communication

Now that inference runs in the same container as the app, the HTTP client/server layer between `inference_client.py` and `inference_server.py` is unnecessary overhead. The server was originally in a separate container, so HTTP was the only option. The separate *process* is still valuable (GPU memory isolation, NF4 weights can't be freed in-process, idle shutdown to reclaim VRAM), but the HTTP layer could be replaced with direct subprocess stdio. The streaming JSONL protocol is already line-based, so the generation tools could spawn the server script directly and read its stdout instead of going through HTTP. This would remove the health check polling, port management, and urllib dependency.

## Slim image variant (no GPU deps)

The full image is ~9 GB, mostly PyTorch + diffusers + ACE-Step. Users who only want chat, browsing, and coding don't need any of that. A `computron_9000:slim` image that skips the GPU layers would be ~3 GB and much faster to pull. Could be a separate Dockerfile stage or a build arg that skips the torch/diffusers/ACE-Step layers.

## Optimize FLUX model downloads

`_download_model()` in `container/inference_server.py` uses `snapshot_download()` which pulls the entire HuggingFace repo. FLUX repos contain both single-file weights (e.g. `flux1-schnell.safetensors`, ~24 GB) and diffusers-sharded weights (`transformer/`, ~24 GB) — downloading both doubles the size from ~34 GB to ~58 GB per model. Use `allow_patterns` to skip single-file weights, or switch to `from_pretrained()` which only fetches what the pipeline needs.
