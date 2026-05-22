# Multi-Provider Support

Allow multiple LLM providers to be configured at once. Every place that picks a model also picks the provider that model runs on — agent profiles, the vision model, the compaction model, the title model. A code expert on Claude and a research agent on DeepSeek via OpenRouter run side by side. There is **no "default provider"** — nothing falls back to a system-wide provider, because every model-chooser carries its own.

## Current state (before this work)

One `llm_provider` + `llm_base_url` in `settings.json`, shared by everything. `config.yaml` has an `llm:` block (`host`, `api_key`, `provider`) and a `summary:` block (`model`, `think`, `options`). Switching providers means reconfiguring the whole app. Vision/compaction/title and the (orphaned) web tools all run on whatever the single global provider is.

## Design

### Two kinds of provider, two storage mechanisms

- **Brokered providers** — OpenAI, Anthropic, OpenRouter, authed OpenAI-compatible. These need credentials, so they're integrations: API key (and base URL for compat) in the vault, a broker process, a socket at `/run/cvault/llm_<name>.sock`, supervisor-managed. This is the existing integrations mechanism, unchanged.
- **Direct providers** — Ollama, and a no-auth OpenAI-compatible endpoint (vLLM, llama.cpp server, LM Studio without auth). No credentials, no broker — just `(name, base_url)`. These are **not** integrations. They live in `settings.json` under a structured `direct_providers` map:
  ```json
  "direct_providers": {
    "ollama": { "base_url": "http://host.docker.internal:11434" },
    "openai_compat": { "base_url": "http://localhost:8000/v1" }
  }
  ```

`config.yaml` carries **no LLM configuration at all** — the `llm:` block and the `summary:` block are both removed, along with the `${LLM_HOST}` / `${LLM_API_KEY}` env wiring. The `http://host.docker.internal:11434` Docker default survives only as a constant the setup wizard pre-fills the Ollama URL field with — not a runtime fallback.

### Settings storage

`settings.json` is the single, complete source of truth — `load_settings()` returns it verbatim and does **not** re-merge `_DEFAULTS`. The file is born complete: `save_settings()`'s first write does `current = load_settings()` which returns a copy of `_DEFAULTS` (no file yet), so the first write is `{**_DEFAULTS, **data}`. New keys added to `_DEFAULTS` in a later release only reach existing installs via a migration — that's deliberate, not a gap (changing a default shouldn't silently change a user's value; if you want to move them, write the migration). We considered making `load_settings()` overlay `_DEFAULTS` and decided against it (it would scatter the effective config between the file and the code).

### Provider registry

`sdk/providers/__init__.py` keeps a `_provider_cache: dict[str, Provider]` keyed by provider name (one cached instance per name; `reset_provider(name=None)` clears one or all).

`get_provider(name)` resolves in order:
1. `name` is in `direct_providers` settings → direct connection to its `base_url`.
2. an `llm_<name>` integration exists with a live broker socket → connect through the socket.
3. otherwise → `ValueError("provider 'name' is not configured — add it on the Providers page")`.

There is no `get_default_provider()` — there is no system-wide default provider.

### Profile provider field

`AgentProfile` and `Agent` each carry `provider: str`. `run_turn` resolves `get_provider(agent.provider)`. `build_agent` errors if a profile has no provider or no model.

`apply_llm_config_to_profiles(model, *, provider, force, context_window)` stamps a chosen LLM config onto profiles (used by the wizard) — gated by `force` or "profile has no model". (The `force` arm exists only for the old wizard re-run; it goes away in the wizard-cleanup step.)

### Per-utility provider + model

Vision, compaction, and title generation each carry their own provider + model in `settings.json`, and the utility code reads those — no global, no `cfg.summary`:

| Utility | Settings keys | Reader |
|---|---|---|
| Vision | `vision_provider`, `vision_model`, `vision_think`, `vision_options` | `sdk/providers/_vision.py` → `get_provider(settings["vision_provider"])` |
| Compaction | `compaction_provider`, `compaction_model`, `compaction_options` | `sdk/context/_strategy.py._resolve_model` → `(provider, model, options)` from settings |
| Title generation | `title_provider`, `title_model` | `conversations/_title_generation.py` → `get_provider(settings["title_provider"])` |

Compaction and title both call `provider.chat(..., think=False)` — no `think` setting for either. Title's inference options are a fixed `{num_predict: 50, temperature: 0.3}` in the code; there's no `title_options` setting. `compaction_threshold` stays a per-profile field.

`config.yaml`'s `summary:` block, `SummaryConfig`, and `_ModelOptions` are deleted (no consumers left).

### API endpoints

- `GET /api/models?provider=X` — `provider` is **required** (no default to fall back to). 400 if it's missing or unknown; 503 with a structured error (`{error, message, provider}`) if it's configured but unreachable, so the wizard / Providers page can show a clear message.
- `POST /api/models/refresh?provider=X` — same, invalidates the per-provider model cache.
- `GET /api/providers` — lists every configured provider: direct ones from `settings.direct_providers` (`kind: "direct"`, `base_url`, `status: "configured"`), brokered ones from the integrations supervisor (`kind: "brokered"`, `status: integration.state`). No `is_default`.
- CRUD for direct providers — either a small set of endpoints or folded into the settings PUT (`direct_providers` is a writable settings field). Brokered providers are managed through the existing integrations API plus the supervisor `update` RPC for key rotation.

### Providers settings page

LLM providers get their **own settings page** (sibling to SystemSettings / Integrations) — they aren't the same kind of thing as Gmail/Calendar/Drive integrations, and they have two storage mechanisms behind them; one page presents them uniformly:

- A row per configured provider: name, status, model count, **test connection**.
- **Add provider**: pick from a catalog. Brokered ones (OpenAI / Anthropic / OpenRouter / authed compat) prompt for an API key (+ base URL for compat) and create an `llm_<name>` integration in the vault. Direct ones (Ollama / no-auth compat) prompt for a base URL and write a `direct_providers` entry.
- Per-provider actions: edit (rotate key for brokered, change base URL for direct), delete.

The **Integrations tab reverts to external-service integrations only** — no LLM providers surfaced there. Brokered providers still use the integrations/supervisor backend (vault + broker + socket) as an implementation detail; they're just not shown in that tab.

**SystemSettings keeps only the model pickers** — default agent, vision, compaction, title — each using the enhanced ModelPicker. The "LLM Provider" connected-status section and the "Setup Wizard re-run" section both go away (providers → Providers page; wizard → first-run only).

### ModelPicker becomes a provider+model selector

- Provider tab bar across the top. Selecting a provider fetches that provider's models (`GET /api/models?provider=`). When only one provider is configured the tab bar is hidden. Model lists are cached per provider so switching tabs doesn't re-fetch.
- Used in ProfileBuilder (per-profile provider+model) and the SystemSettings model pickers (default / vision / compaction / title).
- **`num_ctx` is Ollama-only.** It's a KV-cache allocation knob; OpenAI/Anthropic have a fixed per-model context window with no equivalent. Advanced-options panels show the `num_ctx` field only when the chosen model's provider is `ollama` (the vision panel already does this via a `providers: ['ollama']` tag — reuse it). When an Ollama model is picked, prefill `num_ctx` from the model's reported `context_window` (ModelInfo carries it) rather than a hardcoded default; for non-Ollama providers there is no `num_ctx`. The thing compaction actually needs — the denominator for its fill-ratio threshold — is `num_ctx` when the compaction model is on Ollama, otherwise the model's `context_window` from ModelInfo.
- **Compaction gets an "Advanced" panel** mirroring vision's: editable `compaction_options` (temperature, top_k, num_ctx, num_predict) with the same provider-tagging. No `think` toggle (compaction hardcodes `think=False`).
- **Title gets a model+provider picker only** — no advanced/options panel (its options are fixed and trivial).
- **Fix the ModelPicker results list** so it's a floating popover layered over content — absolute/portal-positioned, its own `z-index`, anchored to the search input. Today it's an inline block in normal flow (`max-height: 260px; overflow-y: auto`), so it pushes the card layout down and gets clipped by the card's `overflow: hidden` / rounded corners (visible on the SystemSettings vision/compaction pickers). Adding the provider tab bar makes the picker taller, so this gets worse if left as-is.

### Setup wizard — first-run only

The wizard configures the first provider once (write a `direct_providers` entry or create an `llm_<name>` integration), plus the initial model picks (stamp the chosen provider+model onto profiles via `apply_llm_config_to_profiles` and seed the `vision_*` / `compaction_*` / `title_*` settings). Once `setup_complete` is true there's no re-run — additional providers are added on the Providers page.

## Steps

### Step 1 — DONE (committed `5a95680`)

Backend plumbing: `_provider_cache` dict + `get_provider(name)` / `reset_provider(name)`; `provider: str` on `AgentProfile` and `Agent`; `run_turn` uses `get_provider(agent.provider)`; `build_agent` requires provider+model; `set_model_on_profiles` → `apply_llm_config_to_profiles` (now takes `provider`); a profile-provider migration; `GET /api/models?provider=X`, `GET /api/providers`; stale test fixtures fixed; the plan doc.

### Step 2 — DONE (staged; `tools/web/` removal committed separately as `36ea517`)

No default provider; provider storage; `config.yaml` cleanup. Includes what earlier drafts split into Steps 2/3/6:

- `LLMConfig` moved out of `config/` into `sdk/providers/_models.py`.
- `config.yaml` loses the `llm:` and `summary:` blocks; `config/` loses `LLMConfig`, `SummaryConfig`, `_ModelOptions`, and `AppConfig.llm` / `AppConfig.summary`; the `${LLM_HOST}` / `${LLM_API_KEY}` env wiring is gone.
- `settings.json` gains `direct_providers`, `vision_provider`, `compaction_provider`, `compaction_options`, `title_provider`, `title_model`; loses `llm_provider` / `llm_base_url`; `direct_providers` base URLs are validated (http/https, not a metadata IP).
- `get_default_provider()` removed; `get_provider(name)` resolves direct → broker socket → error.
- Vision / compaction / title each read their own provider + model (+ options) from settings; `_strategy._resolve_model()` returns `(provider, model, options)`; title gen reads `title_provider`/`title_model` with fixed options.
- `GET /api/models` requires `?provider=`; `GET /api/providers` lists direct + brokered, no `is_default`.
- `tools/web/` deleted (orphaned; was the last `get_default_provider` consumer and a `config.yaml` `summary.model` consumer).
- Migration `_005_multi_provider` (consolidates the earlier `_005`/`_006`): from legacy `settings.llm_provider`/`llm_base_url`, create the `direct_providers` entry for direct kinds; seed `vision_provider`/`compaction_provider`/`title_provider` from the old global provider, `title_model` from the install's existing `compaction_model` (not the old hardcoded `kimi-k2.5:cloud` — that was Ollama-only and silently broke non-Ollama installs), `compaction_options` from the old `summary.options`; drop the legacy keys; stamp every profile with the old provider.
- `SetupWizard.jsx` writes `direct_providers` and seeds the per-use settings; the settings PUT no longer carries `llm_provider`/`llm_base_url`.
- `_settings_routes` resets cached providers when `direct_providers` changes.
- Unit tests updated; `settings.py` gained comments explaining the first-write/source-of-truth model.
- **Known degradation, fixed in Step 3:** SystemSettings and ProfilesTab still `fetch('/api/models')` without a provider, so they show empty model lists until the ModelPicker is provider-aware. e2e wizard/provider tests and `DesktopApp.test.jsx` are not yet updated for the new settings shape.

### Step 3: ModelPicker provider+model selector; fix the degraded UI — DONE

- Provider tab bar in ModelPicker; per-provider model fetch (`GET /api/models?provider=`) with per-provider caching; tab bar hidden when one provider is configured. **DONE.**
- ProfileBuilder passes the configured providers to ModelPicker, stores provider+model on the profile. **DONE.**
- SystemSettings model pickers (default / vision / compaction / title) use the enhanced picker; title gets a model+provider picker, no options panel. **DONE.**
- ProfilesTab stops reading `llm_provider`; ProfileBuilder shows/edits the per-profile provider. **DONE.**
- Fix the ModelPicker results list: floating popover instead of inline-flow. **DONE** (the new picker is a chip trigger with a popover anchored to it).
- Update `DesktopApp.test.jsx` mock + e2e tests for the new settings/picker shape. **DONE.** `tests/e2e/setup/test_wizard_rerun.py` and `tests/e2e/setup/test_wizard_provider_step.py` were deleted — both depended on the removed "Run Setup Wizard" re-entry button. Provider-step conditional-field-visibility coverage is a candidate for future Vitest unit tests on the wizard.
- **Deferred** (not blocking multi-provider; can be picked up later as quality-of-life work):
  - Compaction "Advanced" panel mirroring vision's (editable `compaction_options` with provider-tagged fields). `compaction_options` is still settable by the migration / defaults / hand-editing settings.json; no UI surface.
  - `num_ctx` Ollama-only prefill from the picked model's `context_window` in the advanced panels. Current behavior: hardcoded defaults (60000 for vision, 32768 for compaction).

### Step 4: Providers settings page; revert Integrations tab; wizard first-run-only

- Build the Providers page: list configured providers (status, model count, test connection); add (catalog → API key for brokered, base URL for direct); edit (key rotation / base-URL change); delete.
- Extend the supervisor `update` RPC to accept `auth_blob` for brokered-provider key rotation.
- Revert the Integrations tab to external-service integrations only.
- Remove the "LLM Provider" status section and the "Setup Wizard re-run" section from SystemSettings.
- **Two server endpoints replace the wizard's client-side orchestration:**
  - `POST /api/providers` — configure a provider (direct → write the `direct_providers` entry; brokered → create the `llm_<name>` vault integration), then probe it and return its model list (or a 503 with a clear message). Used by both the Providers page's "add provider" flow and the wizard's provider step. (Today the wizard does the integration POST / settings PUT itself, then a separate `GET /api/models?provider=` — collapse that into one call.)
  - `POST /api/setup/complete` — takes the model picks (`main_model`, `vision_model`); server-side it seeds `vision_provider`/`vision_model`/`compaction_provider`/`compaction_model`/`title_provider`/`title_model`, calls `apply_llm_config_to_profiles` to stamp profiles, and sets `setup_complete` last (so the riskier writes happen before the "done" flag — closer to all-or-nothing than the current `POST /api/profiles/set-model` + `PUT /api/settings` round-trips, which can leave a half-state if the second fails). Replaces the wizard's two finish-step calls.
- Setup wizard: first-run only (drop re-run); a thin client over `POST /api/providers` + `POST /api/setup/complete`.
- Drop the `force` param from `apply_llm_config_to_profiles` and the `updateAllProfiles` checkbox from the wizard (re-run only). First run still calls `apply_llm_config_to_profiles(model, provider=...)` (now from inside `POST /api/setup/complete`) to fill the shipped default profiles; after that, profiles are edited individually in ProfileBuilder, and changing a provider's connection on the Providers page never bulk-rewrites profiles.
- Remove the wizard's "remove any existing LLM integration" pre-step and the "one provider active at a time" framing — vestiges of the single-provider model; `POST /api/providers` just adds what was picked.

## Edge cases

**Provider not configured**: `get_provider(name)` raises `ValueError` pointing to the Providers page; `/api/models` turns that into a 400. The frontend also validates provider selection at profile-save time, and `build_agent` errors before a turn starts.

**Direct-provider URL validation**: the base URL must be `http`/`https` and must not target a metadata-service IP — the `_BLOCKED_HOSTS` check that was on `llm_base_url` is now on the `direct_providers` write path (`SettingsUpdate._validate_direct_providers`).

**Fresh install**: zero providers until the wizard runs. The wizard's first `PUT /api/settings` creates `settings.json` (born with the full `_DEFAULTS` set, plus the chosen `direct_providers`); the finish step writes `setup_complete` + the per-use provider/model picks and stamps profiles. Until then `/api/providers` is empty and the app blocks on the wizard, same as today.

**Reasoning-model temperature**: OpenAI reasoning models (o1/o3/gpt-5) reject `temperature != 1`, and `_openai_responses.py` sets `temperature` unconditionally when present — so picking such a model for vision/compaction/title (or an agent) with a non-1 temperature 400s. That's a provider-layer gap (it predates this work and isn't specific to any one utility); fix it where options are translated, not here.

**API key rotation**: extend the supervisor's `update` RPC to accept `auth_blob` (re-encrypt, restart broker). Simpler fallback: delete + re-add the provider.
