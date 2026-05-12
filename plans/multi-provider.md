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

### Provider registry

`sdk/providers/__init__.py` keeps a `_provider_cache: dict[str, Provider]` keyed by provider name (one cached instance per name; `reset_provider(name=None)` clears one or all).

`get_provider(name)` resolves in order:
1. `name` is in `direct_providers` settings → direct connection to its `base_url`.
2. an `llm_<name>` integration exists with a live broker socket → connect through the socket.
3. otherwise → `ValueError("provider 'name' is not configured — add it on the Providers page")`.

`get_default_provider()` is **removed**. There is no system-wide default provider.

### Profile provider field

`AgentProfile` and `Agent` each carry `provider: str`. `run_turn` resolves `get_provider(agent.provider)`. `build_agent` errors if a profile has no provider or no model.

`apply_llm_config_to_profiles(model, *, provider, force, context_window)` stamps a chosen LLM config onto profiles (used by the wizard) — gated by `force` or "profile has no model".

### Per-utility provider + model

Vision, compaction, and title generation each get their own provider + model in `settings.json`, and the utility code reads those instead of any global:

| Utility | Settings keys | Reader |
|---|---|---|
| Vision | `vision_provider`, `vision_model`, `vision_think`, `vision_options` | `sdk/providers/_vision.py` → `get_provider(settings["vision_provider"])` |
| Compaction | `compaction_provider`, `compaction_model`, `compaction_think`, `compaction_options` | `sdk/context/_strategy.py` reads all from settings; no `cfg.summary` |
| Title generation | `title_provider`, `title_model` | `conversations/_title_generation.py` → `get_provider(settings["title_provider"])`; no `cfg.summary.model` |

(`vision_think` / `vision_options` already exist as settings. `compaction_think` / `compaction_options` are new — they replace what compaction currently borrows from `config.yaml` `summary.options` / `summary.think`. `compaction_threshold` stays a per-profile field, unchanged.)

After this, `config.yaml`'s `summary:` block has no consumers; it and `SummaryConfig` are deleted.

### API endpoints

- `GET /api/models?provider=X` — `provider` is **required** (no default to fall back to). 503 with a structured error if the provider is unreachable, so the wizard / Providers page can show a clear message.
- `POST /api/models/refresh?provider=X` — same, invalidates the per-provider model cache.
- `GET /api/providers` — lists every configured provider (direct ones from `settings.direct_providers`, brokered ones from the integrations supervisor) with status and model count. No `is_default` flag.
- CRUD for direct providers (`settings.direct_providers` entries) — a small set of endpoints or folded into the settings PUT. Brokered providers are managed through the existing integrations API plus the supervisor `update` RPC for key rotation.

### Providers settings page

LLM providers get their **own settings page** (sibling to SystemSettings / Integrations) — they aren't the same kind of thing as Gmail/Calendar/Drive integrations, and they now have two storage mechanisms behind them; one page presents them uniformly:

- A row per configured provider: name, status, model count, **test connection**.
- **Add provider**: pick from a catalog. Brokered ones (OpenAI / Anthropic / OpenRouter / authed compat) prompt for an API key (+ base URL for compat) and create an `llm_<name>` integration in the vault. Direct ones (Ollama / no-auth compat) prompt for a base URL and write a `direct_providers` entry.
- Per-provider actions: edit (rotate key for brokered, change base URL for direct), delete.

The **Integrations tab reverts to external-service integrations only** — no LLM providers surfaced there. Brokered providers still use the integrations/supervisor backend (vault + broker + socket) as an implementation detail; they're just not shown in that tab.

**SystemSettings keeps only the model pickers** — default agent, vision model+provider, compaction model+provider, title model+provider — each using the enhanced ModelPicker. The provider-connection section that's in SystemSettings today moves to the Providers page.

### ModelPicker becomes a provider+model selector

- Provider tab bar across the top. Selecting a provider fetches that provider's models. When only one provider is configured the tab bar is hidden. Model lists are cached per provider so switching tabs doesn't re-fetch.
- Used in ProfileBuilder (per-profile provider+model) and in the SystemSettings model pickers (default / vision / compaction / title).
- **Fix the results list** so it's a floating popover layered over content — absolute/portal-positioned, its own `z-index`, anchored to the search input. Today it's an inline block in normal flow (`max-height: 260px; overflow-y: auto`), so it pushes the card layout down and gets clipped by the card's `overflow: hidden` / rounded corners (visible on the SystemSettings vision/compaction pickers). Adding the provider tab bar makes the picker taller, so this gets worse if left as-is.

### Setup wizard — first-run only

The wizard drives the Providers "add provider" flow once for the first provider, plus the initial model picks (which stamp the chosen provider+model onto profiles via `apply_llm_config_to_profiles` and seed the `vision_*` / `compaction_*` / `title_*` settings). Once `setup_complete` is true there's no re-run — additional providers are added on the Providers page.

## Steps

### Step 1: Backend plumbing — DONE (uncommitted on branch `multi-provider`)

- Dict-based provider cache: `get_provider(name)`, `reset_provider(name)` — done.
- `provider: str` on `AgentProfile` and `Agent`; `run_turn` uses `get_provider(agent.provider)`; `build_agent` requires both — done.
- `apply_llm_config_to_profiles` (renamed from `set_model_on_profiles`, now takes `provider`) — done. Wizard passes `provider`.
- Startup migration `migrations/_005_profile_provider.py` stamps existing profiles with the legacy `settings.llm_provider` — done.
- `GET /api/models?provider=X`, `GET /api/providers` — done (still has a default fallback that Step 2 removes).
- Tests updated — done.
- **Superseded by later steps:** Step 1 added `get_default_provider()` and points the utility callers at it as a stepping stone; Step 2 removes it. The `_005` migration currently only stamps profiles; Step 2 extends the migration to also create provider entries and seed the per-utility settings.

### Step 2: No default provider; provider storage; `config.yaml` cleanup

- Add `direct_providers` to `settings.json` (structured map).
- `get_provider(name)` resolves direct → integration → error, per the design above.
- Remove `get_default_provider()`, `settings.llm_provider`, `settings.llm_base_url` (and `_LLM_FIELDS` / the `reset_provider()`-on-change hook keyed off them in `_settings_routes.py`).
- Remove the `llm:` block from `config.yaml` and `LLMConfig` from `config/__init__.py`; drop the `${LLM_HOST}` / `${LLM_API_KEY}` env wiring. Keep the Docker-default URL as a wizard pre-fill constant.
- `GET /api/models` makes `?provider=` required (drop the default fallback).
- `GET /api/providers` drops `is_default`; merges direct (settings) + brokered (supervisor) sources.
- Extend migration `_005` (or add `_006`): from legacy `settings.llm_provider` / `llm_base_url` + old `config.yaml` `llm.*`, create the equivalent `direct_providers` entry (Ollama / no-auth compat) — brokered providers already have their integration — then delete the legacy settings keys. Profiles were already stamped in Step 1; also seed `vision_provider` / `compaction_provider` / `title_provider` to that same provider here so the per-utility settings aren't empty after upgrade.

### Step 3: Per-utility provider + model + inference options

- Add `vision_provider`, `compaction_provider`, `compaction_think`, `compaction_options`, `title_provider`, `title_model` to settings (and `compaction_model` already exists).
- `_vision.py`, `_strategy.py`, `_title_generation.py` read their own provider + model (+ options) from settings — none of them call `get_default_provider()` or `cfg.summary` anymore.
- Migration seeds `compaction_options` / `compaction_think` from the old `config.yaml` `summary.options` / `summary.think` (and `vision_*` from existing settings, `title_*` from the legacy provider + the old `summary.model`), then deletes the `summary:` block from `config.yaml` and `SummaryConfig` from `config/__init__.py`.

### Step 4: ModelPicker provider+model selector

- Provider tab bar, per-provider model fetching with caching, tabs hidden when one provider.
- ProfileBuilder passes the configured providers to ModelPicker, stores provider+model.
- SystemSettings model pickers (default / vision / compaction / title) use the enhanced picker.
- Fix the results list: floating popover instead of inline-flow (so it overlays instead of reflowing/clipping).

### Step 5: Providers settings page; revert Integrations tab; wizard first-run-only

- Build the Providers page: list configured providers (status, model count, test connection); add (catalog → API key for brokered, base URL for direct); edit (key rotation / base URL change); delete.
- Extend the supervisor `update` RPC to accept `auth_blob` for brokered-provider key rotation.
- Revert the Integrations tab to external-service integrations only — drop any LLM-provider surfacing there.
- Remove the provider-connection section from SystemSettings (it lives on the Providers page now).
- Setup wizard: first-run only (drop the re-run capability); becomes a thin wrapper over the Providers add-provider flow + the initial model picks.
- Drop the `force` parameter from `apply_llm_config_to_profiles` and the `updateAllProfiles` checkbox from the wizard — both existed only for wizard re-run. First run still calls `apply_llm_config_to_profiles(model, provider=...)` to fill in the shipped default profiles (which ship with empty `provider`/`model`); after that, each profile's provider+model is edited individually in ProfileBuilder. Changing a provider's connection config on the Providers page never bulk-rewrites profiles.

### Step 6: Remove orphaned web tools

`tools/web/` (`get_webpage`, `get_webpage_raw`, `html_find_elements`, `summarize`, `types`) isn't wired into any agent toolset or skill — nothing imports it except its own unit tests, and it was the second consumer of `config.yaml`'s `summary.model`. Independent of the rest; bundled here because it's the same surface.

- Delete the `tools/web/` package.
- Delete `tests/unit/tools/web/`.
- No dedicated settings to remove — the web tools reused the `summary:` block, which Step 3 already removes.

## Edge cases

**Provider not configured**: `get_provider(name)` raises `ValueError` pointing to the Providers page. The frontend also validates provider selection at profile-save time, and `build_agent` errors before a turn starts.

**Direct-provider URL validation**: the base URL must be `http`/`https` and must not target a metadata-service IP (the existing `_BLOCKED_HOSTS` check that's on `llm_base_url` today moves to the `direct_providers` write path).

**Fresh install**: zero providers until the wizard runs. The wizard creates the first provider (direct or brokered) and seeds the per-utility settings + profiles from it. Until then `/api/providers` returns empty and the app blocks on the wizard, same as today.

**API key rotation**: extend the supervisor's `update` RPC to accept `auth_blob` (re-encrypt, restart broker). Simpler fallback: delete + re-add the provider.

**Migration ordering**: Step 1's `_005` already ran on installs that updated mid-development — it stamped profiles from `settings.llm_provider`. Step 2/3's migration work must be idempotent and tolerate profiles that already have a provider, and must read the legacy settings keys *before* they're deleted (do the create-provider-entry + seed-per-utility-settings work in the same migration that removes the legacy keys).
