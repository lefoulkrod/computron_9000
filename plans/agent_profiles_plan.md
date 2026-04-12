# Agent Profiles Implementation Plan

## Overview

Replace the current per-session model settings panel with **Agent Profiles** — reusable
configurations that bundle model, system prompt, skills, and inference parameters into a
single selectable unit. Profiles become the primary way users configure agent behavior
for chat, sub-agents, and autonomous tasks.

## Key Design Decisions

- **Computron profile is locked.** It's the system default — viewable but not editable.
  Users can duplicate it to create a customizable copy.
- **Model lives inside profiles.** Every profile specifies its own model. The Computron
  profile's model is set during the setup wizard. Changing the "default model" in
  System settings writes directly to the Computron profile. No fallback/None logic.
- **Shipped profiles are fully editable.** Code Expert, Research Agent, Creative Writer,
  etc. ship as JSON files but users can modify them freely.
- **Inference presets are UI-only.** The Balanced/Creative/Precise/Code buttons in the
  profile builder just fill in parameter values. The profile stores the actual numbers,
  not a preset reference. On edit, the builder matches saved values against preset
  definitions to highlight the matching one (or none if custom).
- **Profile selector replaces ModelSettingsPanel.** A compact picker near the chat input
  replaces the current right-panel settings. The full profile builder lives in
  Settings > Agent Profiles.
- **Tasks migrate from `agent` to `agent_profile`.** Since the `skills`/`profile`
  intermediate format was never shipped, we migrate directly from the old `agent` field.
- **First-time setup wizard.** On first launch, users must pick a main model and vision
  model before using the app. Saved to config, changeable in Settings > System.

---

## Phase 1: Backend — Models API + Profile Data Model

### 1.1 Enriched Models API

**Goal:** `/api/models` returns model metadata from Ollama, with filtering support.

**New endpoint:** `GET /api/models?capability=vision`

**Changes:**

- `sdk/providers/_ollama.py` — add `list_models_detailed()` method:
  - Call `self._client.list()` to get all models
  - For each model, call `self._client.show(model.model)` to get capabilities
  - Return list of dicts with: `name`, `parameter_size`, `quantization_level`,
    `family`, `capabilities` (list of strings from show response),
    `is_cloud` (derived from `:cloud` suffix in name)
  - Cache results in memory (invalidated on explicit refresh)

- `sdk/providers/_base.py` (or protocol) — add `list_models_detailed()` to provider
  interface with default falling back to basic `list_models()`

- `server/aiohttp_app.py` — update `list_models_handler`:
  - Call `provider.list_models_detailed()`
  - If `?capability=X` query param, filter to models where capabilities includes X
  - Add `POST /api/models/refresh` to invalidate cache
  - Response shape:
    ```json
    {
      "models": [
        {
          "name": "qwen3:32b",
          "parameter_size": "32B",
          "quantization_level": "Q4_K_M",
          "family": "qwen3",
          "capabilities": ["completion", "tools"],
          "is_cloud": false
        },
        {
          "name": "gemma3:12b",
          "parameter_size": "12B",
          "quantization_level": "Q4_K_M",
          "family": "gemma",
          "capabilities": ["completion", "tools", "vision"],
          "is_cloud": false
        }
      ]
    }
    ```

### 1.2 AgentProfile Data Model

**Goal:** Define the `AgentProfile` Pydantic model and persistence layer.

**New file:** `agents/_agent_profiles.py`

```python
class AgentProfile(BaseModel):
    id: str
    name: str
    description: str = ""
    icon: str = ""
    system: bool = False          # True only for Computron — locked
    system_prompt: str = ""       # Full system prompt for this profile
    model: str                    # Every profile must have a model
    skills: list[str] = Field(default_factory=list)
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    repeat_penalty: float | None = None
    num_predict: int | None = None
    think: bool | None = None
    num_ctx: int | None = None    # Context window in tokens
    max_iterations: int | None = None
```

**Functions:**
- `list_agent_profiles() -> list[AgentProfile]`
- `get_agent_profile(profile_id: str) -> AgentProfile | None`
- `save_agent_profile(profile: AgentProfile) -> AgentProfile` — validates, writes JSON
- `delete_agent_profile(profile_id: str) -> bool` — prevents deleting system profile
- `get_default_profile() -> AgentProfile` — returns Computron
- `build_llm_options(profile) -> LLMOptions` — converts profile fields to LLMOptions

**Persistence:**
- User/edited profiles stored in `{settings.home_dir}/agent_profiles/` as `{id}.json`
- Shipped profiles kept in `agents/default_profiles/` in the repo — these are the
  read-only originals that can be used for a future "restore to default" feature
- On first run, shipped profiles are copied to the state folder. User edits go to
  the state folder copy. The originals in the repo are never modified.
- Computron profile is also written to disk on first run but the API rejects
  edits/deletes (system=true). Keeps it simple and consistent.

**Shipped profiles (JSON files in `agents/default_profiles/`):**
- `computron.json` — system=true, no skills (loads on demand), model set by
  setup wizard. Changing the default model in System settings updates this
  profile's model field directly.
- `code_expert.json` — skills=["coder"], temperature=0.3, think=true
- `research_agent.json` — skills=["browser", "coder"], temperature=0.5
- `creative_writer.json` — temperature=1.0, top_p=0.95

**Delete `agents/_profiles.py`** — the old `InferenceProfile` system. Remove
`InferenceProfile` from `agents/types.py`. Update `agents/__init__.py` exports.

### 1.3 Profile CRUD API

**New routes in `server/aiohttp_app.py`:**

- `GET /api/profiles` — list all profiles
- `GET /api/profiles/{id}` — get single profile
- `POST /api/profiles` — create new profile (body = AgentProfile JSON)
- `PUT /api/profiles/{id}` — update profile (rejects if system=true)
- `DELETE /api/profiles/{id}` — rejects if system=true. Before deleting, checks
  if any tasks reference this profile. If so, returns 409 with the list of
  tasks/goals using it. Frontend shows a modal listing the affected tasks with
  two options: edit tasks individually, or bulk-reassign all to a different
  profile (dropdown in the modal). Delete proceeds only after no tasks reference it.
- `POST /api/profiles/{id}/duplicate` — clone a profile with new ID/name
- `GET /api/profiles/{id}/usage` — returns list of goals/tasks referencing this
  profile (used by the delete confirmation modal)

### 1.4 Settings File

**Goal:** Single `settings.json` in the state folder for all app settings.
The setup wizard writes to it, and it's the settings file for everything.

**File:** `{settings.home_dir}/settings.json`

```json
{
  "setup_complete": true,
  "default_model": "qwen3:32b",
  "vision_model": "gemma3:12b"
}
```

**Changes to `config/__init__.py`:**
- Load `settings.json` from state folder
- Expose via `load_config().settings.default_model`, `.vision_model`,
  `.setup_complete`
- If file doesn't exist or `setup_complete` is false, wizard is required

**New routes:**
- `GET /api/settings` — returns full settings
- `PUT /api/settings` — update settings (partial update, merges with existing)
- Used by both the setup wizard and the System settings tab

---

## Phase 2: Backend — Profile Integration

### 2.1 Chat Request Flow

**Goal:** Chat requests send `profile_id` instead of raw LLMOptions.

**Changes to `server/aiohttp_app.py`:**
- `ChatRequest` model: replace `options: LLMOptions | None` with
  `profile_id: str | None = None`

**Changes to `server/message_handler.py`:**
- `handle_user_message()` — replace `options` parameter with `profile_id`
- Load profile via `get_agent_profile(profile_id)`, fall back to Computron default
- Build LLMOptions via `build_llm_options(profile)`
- `_build_agent()` — use profile's system_prompt as the agent's full system prompt
- Pre-load profile's skills into AgentState

### 2.2 spawn_agent Changes

**Changes to `sdk/tools/_spawn_agent.py`:**
- `profile` param semantics change: now references an `AgentProfile` ID
- Load full AgentProfile → get model, skills, inference params, system_prompt
- If profile not found, warning log and fall back to parent's options
- Agent uses `profile.system_prompt` directly — no layering or appending

### 2.3 Task System Migration

**Goal:** Tasks reference `agent_profile` instead of `agent`.

Since the `skills`/`profile` intermediate format was never shipped to users, we
migrate directly from the old format where tasks stored `agent: str` (e.g.
"browser", "coder", "computron").

**Changes to `tasks/_models.py`:**
- Replace `skills: list[str]` and `profile: str | None` with
  `agent_profile: str | None = None`
- Remove `agent_config: dict | None` — profiles replace all configuration

**Changes to `tasks/_file_store.py`:**
- Update `_migrate_task_data()`:
  ```python
  # Old format: agent field → map to shipped profile
  if "agent" in t and "agent_profile" not in t:
      agent = t.pop("agent")
      agent_to_profile = {
          "browser": "research_agent",
          "coder": "code_expert",
          "computron": None,  # uses default
      }
      profile_id = agent_to_profile.get(agent)
      if profile_id:
          t["agent_profile"] = profile_id
  # Also handle intermediate format if any test data exists
  if "skills" in t and "agent_profile" not in t:
      t.pop("skills", None)
      t.pop("profile", None)
  ```
- Apply migration in `list_tasks()` and `get_task()` — write back on read

**Changes to `tasks/_executor.py`:**
- `_build_agent()` — load `AgentProfile` by ID, extract skills + inference params +
  system prompt, build agent from those
- Remove direct `apply_profile()` calls (old InferenceProfile system)

**Changes to `tasks/_tools.py`:**
- `add_task()` — replace `skills` and `profile` params with
  `agent_profile: str | None = None`
- Validate agent_profile ID exists in registry at creation time
- `create_goal()` — same change in task dict schema

**Changes to `skills/goal_planner.py`:**
- Update `_SKILL` prompt to document `agent_profile` parameter instead of
  `skills` + `profile`

**Test updates:**
- `tests/tasks/test_models.py` — update for `agent_profile` field
- `tests/tasks/test_tools.py` — update for `agent_profile` parameter

---

## Phase 3: Frontend — Settings Page + Profile Builder

### 3.1 Settings Page Shell

**Goal:** Gear icon in sidebar opens a full settings view with tabs.

**New components:**
- `server/ui/src/components/SettingsPage.jsx` — tab container
- `server/ui/src/components/SettingsPage.module.css`

**Tabs:** Agent Profiles | System | Features

**Changes to `server/ui/src/components/Sidebar.jsx`:**
- "settings" panel opens SettingsPage as a full view (not flyout)

**Changes to `server/ui/src/DesktopApp.jsx`:**
- When sidebar "settings" is active, render SettingsPage instead of chat area
- Remove ModelSettingsPanel from flyout panel

### 3.2 System Settings Tab

**Goal:** Configure system default model and vision model.

**New component:** `server/ui/src/components/SystemSettings.jsx`

**Sections:**
- **Models** — Computron Model dropdown (all models), Vision Model dropdown
  (filtered to `capability=vision`). Note: "Agent profiles can override this
  with their own model."
- **Ollama Connection** — status indicator, model count, refresh button
- **Setup** — "Run Setup Wizard" button

**Data fetching:**
- `GET /api/models` for all models
- `GET /api/models?capability=vision` for vision dropdown
- `GET /api/settings` for current settings
- `PUT /api/settings` to save changes

### 3.3 Agent Profiles Tab — List + Builder

**Goal:** Master-detail layout: profile list on left, builder/viewer on right.

**New components:**
- `server/ui/src/components/ProfileList.jsx` — left column with profile cards
- `server/ui/src/components/ProfileBuilder.jsx` — editor form
- `server/ui/src/components/ProfileList.module.css`
- `server/ui/src/components/ProfileBuilder.module.css`

**New hook:** `server/ui/src/hooks/useAgentProfiles.js`
- Fetches `GET /api/profiles` on mount
- CRUD operations via API
- Tracks selected profile ID
- Tracks dirty state for unsaved changes

**Profile list:**
- Computron at top, separated by divider, gold `🔒 system` badge
- Other profiles below with skill badges and param previews
- "+ New" button in header
- Click profile to view/edit

**Profile builder (editable profile):**
- Identity: icon picker, name input, description input
- Model: dropdown from `/api/models`
- System Prompt: textarea
- Skills: toggleable chip grid (from `/api/skills` or hardcoded list)
- Inference Preset: Balanced/Creative/Precise/Code buttons
- Advanced Settings (collapsed): temperature, top_k, top_p, repeat_penalty,
  context, max_output, iterations, thinking toggles
- Actions: Delete (left), Duplicate, Revert, Save (right)

**Profile viewer (Computron selected):**
- Same layout but all fields read-only/dimmed
- Gold locked banner at top with Duplicate button
- Duplicate CTA at bottom
- Model shows "Uses system default (model_name) — change in System settings"

**Preset matching on edit:**
```javascript
const PRESETS = {
  balanced: { temperature: 0.7 },
  creative: { temperature: 1.0, top_p: 0.95 },
  precise:  { temperature: 0.2, top_k: 40 },
  code:     { temperature: 0.3, think: true },
};

function matchPreset(profile) {
  for (const [id, values] of Object.entries(PRESETS)) {
    const match = Object.entries(values).every(([k, v]) => profile[k] === v)
      && Object.keys(PRESETS)
           .flatMap(pid => Object.keys(PRESETS[pid]))
           .filter(k => !(k in values))
           .every(k => profile[k] == null);
    if (match) return id;
  }
  return null;
}
```

**Help panel:** Right column, static — shows help for all settings in the same
order they appear in the editor. Always visible, no click-to-reveal.

### 3.4 Profile Selector in Chat View

**Goal:** Compact profile picker below chat input, near existing buttons.

**New component:** `server/ui/src/components/ProfileSelector.jsx`
- Dropdown or popover showing available profiles with icons
- Shows currently active profile name + icon
- Switching profiles applies immediately to next message

**Changes to `server/ui/src/components/ChatInput.jsx`:**
- Add ProfileSelector alongside existing attachment/send buttons
- Pass `selectedProfileId` and `onProfileChange` props

**Changes to `server/ui/src/DesktopApp.jsx`:**
- Replace `useModelSettings` with profile-based state
- `selectedProfileId` in state, persisted to localStorage
- `handleSend` passes `profile_id` to `sendMessage` instead of `modelSettings`

**Changes to `server/ui/src/hooks/useStreamingChat.js`:**
- `_buildRequestBody()` sends `profile_id` instead of inline options
- Remove all the individual option extraction (temperature, topK, etc.)
- Simplified: `body.profile_id = profileId`

### 3.5 Remove Old Settings

**Delete:**
- `server/ui/src/components/ModelSettingsPanel.jsx`
- `server/ui/src/components/ModelSettingsPanel.module.css`
- `server/ui/src/hooks/useModelSettings.js`

**Clean up:**
- `DesktopApp.jsx` — remove `useModelSettings`, flyout for settings panel
- `MobileApp.jsx` — same cleanup, add ProfileSelector to mobile layout

---

## Phase 4: Frontend — Setup Wizard

### 4.1 Wizard Component

**Goal:** Full-screen wizard on first launch. Four steps.

**New components:**
- `server/ui/src/components/SetupWizard.jsx`
- `server/ui/src/components/SetupWizard.module.css`

**Steps:**
1. **Welcome** — icon, title, subtitle
2. **Main Model** — radio-select cards with metadata badges (param size,
   quantization, family, cloud tag). Data from `GET /api/models`.
3. **Vision Model** — same card format, filtered to `GET /api/models?capability=vision`.
4. **Ready** — confirmation summary, "Start Chatting" button

**Flow:**
- No skip — both selections required
- Back button on steps 2-3
- On completion: `PUT /api/settings` with selections

**Changes to `server/ui/src/DesktopApp.jsx`:**
- On mount, check `GET /api/settings`
- If `setup_complete: false` (or missing), render SetupWizard instead of normal app
- On wizard completion, transition to chat view

---

## Phase 5: Cleanup + Migration

### 5.1 Remove Old Profile System

- Delete `agents/_profiles.py`
- Remove `InferenceProfile` from `agents/types.py`
- Update `agents/__init__.py` — remove profile exports, add agent profile exports
- Remove preset cards from deleted ModelSettingsPanel

### 5.2 Remove persist_thinking

Remove `persist_thinking` entirely — thinking is always persisted in
conversation history (the conditional logic was a failed experiment).
Delete all code that checks or toggles this flag.

- `agents/types.py` — remove from `LLMOptions` and `Agent`
- `server/message_handler.py` — remove persist_thinking handling, thinking
  always goes into history
- `sdk/tools/_spawn_agent.py` — remove persist_thinking from agent construction
- `sdk/tools/_agent_wrapper.py` — remove persist_thinking references
- `sdk/turn/_execution.py` — remove conditional persist_thinking logic,
  always persist thinking
- `server/ui/src/hooks/useStreamingChat.js` — remove from `_buildRequestBody`
- `server/ui/src/hooks/useModelSettings.js` — remove (file is being deleted
  anyway in 3.5)
- `tests/sdk/test_tool_loop_serialization.py` — update tests

### 5.2 Update Computron Agent

- `agents/computron/agent.py` — update `spawn_agent` documentation in system
  prompt to reference agent profiles instead of inference profiles
- System prompt mentions `spawn_agent(..., profile="code_expert")` pattern

### 5.3 Task Data Migration

- `tasks/_file_store.py` — `_migrate_task_data()` handles:
  - `agent: "browser"` → `agent_profile: "research_agent"`
  - `agent: "coder"` → `agent_profile: "code_expert"`
  - `agent: "computron"` → `agent_profile: None` (system default)
  - Write migrated data back on read
- `tasks/_store.py` — update protocol for new signature

### 5.4 Config Cleanup

- `config.yaml` — remove `vision.model` default (now in settings.json)
- `config/__init__.py` — load `settings.json` from state folder for
  `default_model`, `vision_model`, `setup_complete`
- Vision model consumer (`tools/virtual_computer/describe_image.py`) reads from
  settings.json instead of `config.vision.model`

---

## Implementation Order

1. **Phase 1.1** — Enriched models API (backend, no UI changes)
2. **Phase 1.2** — AgentProfile model + persistence + shipped profiles
3. **Phase 1.3** — Profile CRUD API
4. **Phase 1.4** — Settings file (settings.json in state folder)
5. **Phase 4** — Setup wizard (frontend, blocks on 1.1 + 1.4)
6. **Phase 3.1** — Settings page shell + sidebar changes
7. **Phase 3.2** — System settings tab
8. **Phase 3.3** — Profile list + builder
9. **Phase 3.4** — Profile selector in chat + request flow changes
10. **Phase 2.1** — Chat request uses profile_id
11. **Phase 2.2** — spawn_agent uses agent profiles
12. **Phase 2.3** — Task system migration
13. **Phase 5** — Cleanup old code
14. **Phase 3.5** — Remove old settings components

---

## Files Changed Summary

### New Files
- `agents/_agent_profiles.py` — AgentProfile model, registry, persistence
- `agents/default_profiles/` — shipped profile JSON files
- `server/ui/src/components/SettingsPage.jsx` + `.module.css`
- `server/ui/src/components/SystemSettings.jsx` + `.module.css`
- `server/ui/src/components/ProfileList.jsx` + `.module.css`
- `server/ui/src/components/ProfileBuilder.jsx` + `.module.css`
- `server/ui/src/components/ProfileSelector.jsx` + `.module.css`
- `server/ui/src/components/SetupWizard.jsx` + `.module.css`
- `server/ui/src/hooks/useAgentProfiles.js`

### Modified Files
- `sdk/providers/_ollama.py` — `list_models_detailed()`
- `server/aiohttp_app.py` — new routes, updated chat handler
- `server/message_handler.py` — profile-based agent building
- `agents/types.py` — remove InferenceProfile
- `agents/__init__.py` — updated exports
- `agents/computron/agent.py` — updated system prompt
- `sdk/tools/_spawn_agent.py` — profile references AgentProfile
- `tasks/_models.py` — `agent_profile` field
- `tasks/_tools.py` — `agent_profile` parameter
- `tasks/_executor.py` — build agent from AgentProfile
- `tasks/_file_store.py` — migration from `agent` to `agent_profile`
- `tasks/_store.py` — updated protocol
- `skills/goal_planner.py` — updated skill prompt
- `config/__init__.py` — SetupConfig
- `server/ui/src/DesktopApp.jsx` — settings view, profile state, wizard gate
- `server/ui/src/MobileApp.jsx` — profile state, remove old settings
- `server/ui/src/components/Sidebar.jsx` — settings opens full view
- `server/ui/src/components/ChatInput.jsx` — profile selector
- `server/ui/src/hooks/useStreamingChat.js` — send profile_id

### Deleted Files
- `agents/_profiles.py`
- `server/ui/src/components/ModelSettingsPanel.jsx`
- `server/ui/src/components/ModelSettingsPanel.module.css`
- `server/ui/src/hooks/useModelSettings.js`

### Test Updates
- `tests/tasks/test_models.py`
- `tests/tasks/test_tools.py`
