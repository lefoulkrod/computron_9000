# Plan: Single Orchestrator + Skills + Profiles

## Context

The current system has multiple hardcoded agents (computron, browser, coder, goal_planner, desktop) each with static tool sets and system prompts. The goal is to collapse this into **one root agent** that can load skills on demand and spawn focused sub-agents — no more agent selection in the UI. The `computron_skills` agent already proves this pattern works.

Beyond that:
- **Profiles**: named presets for inference parameters (temperature, top_k, etc.) that can be attached to agents or goal tasks, decoupling tuning from global app settings
- **Goal system integration**: goal tasks currently pick from hardcoded agents — they should use skills + profiles instead
- **Goal creation as a skill**: the goal planner agent becomes a loadable skill

---

## Phase 1: Profiles — named inference parameter presets

### What changes

**New model: `InferenceProfile`** (in `agents/types.py`)

```python
class InferenceProfile(BaseModel):
    id: str                          # "creative", "precise", "code", etc.
    name: str                        # display name
    description: str                 # when to use this profile
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    repeat_penalty: float | None = None
    num_predict: int | None = None
    reasoning_effort: str | None = None
    think: bool | None = None
    max_iterations: int | None = None
```

Model is intentionally excluded — model stays global (UI/config selected).

**Profile registry** (`agents/_profiles.py`):
- `register_profile()`, `get_profile()`, `list_profiles()`
- Ship a few built-in profiles: "balanced" (default), "creative" (higher temp), "precise" (low temp, high top_k), "code" (low temp, thinking on)
- Profiles persisted in `~/.computron_9000/profiles/` so users can create their own

**Apply profiles**: When building an `Agent`, a profile's values fill in as defaults, then per-request `LLMOptions` override on top. Priority: `per-request options > profile > app defaults`.

**Wire into `spawn_agent()`**: Add optional `profile` parameter so sub-agents can use different inference settings than the parent.

**Wire into goal tasks**: `Task` model gets `profile: str | None`. `TaskExecutor` applies the profile. `add_task()` gets a `profile` parameter.

### Files

| File | Change |
|------|--------|
| `agents/types.py` | Add `InferenceProfile` model |
| `agents/_profiles.py` | New — profile registry + built-in profiles |
| `agents/__init__.py` | Export new types |
| `sdk/tools/_spawn_agent.py` | Add `profile` param, apply before building Agent |
| `tasks/_models.py` | Add `profile` field to `Task` |
| `tasks/_tools.py` | Add `profile` param to `add_task()` and `create_goal()` |
| `tasks/_executor.py` | Apply profile when building agent for task execution |
| `server/message_handler.py` | Apply profile in `_build_agent()` |

---

## Phase 2: Single root agent with skill loading

### What changes

**Merge `computron_skills` into `computron`**: The skill-based orchestrator becomes the only root agent. Its system prompt covers orchestration (delegation, planning, spawn_agent, load_skill) while skill prompts cover tool-specific instructions.

**Goal planner becomes a skill** (`skills/goal_planner.py`):
- Tools: `begin_goal`, `add_task`, `commit_goal`, `list_goals`, `list_tasks`, `trigger_goal`
- Prompt: instructions for creating well-structured goals with proper task decomposition
- The root agent loads it on demand via `load_skill("goal_planner")` when the user wants to set up autonomous tasks

**Remove agent selection from the API**: The `/api/agents` endpoint no longer returns a list of selectable agents. The `agent` field in `ChatRequest` is removed (or ignored). There's one root agent.

**Update the root agent's system prompt** to document:
- `load_skill(name)` — add tools to current context for quick tasks
- `spawn_agent(instructions, skills, profile)` — isolated sub-agent for heavy lifting
- Available skills (dynamically listed from registry)
- Available profiles (dynamically listed)

**Remove hardcoded agent-as-tool wrappers**: `computer_agent_tool`, `browser_agent_tool`, `desktop_agent_tool`, `goal_planner_tool` are deleted. The root agent uses `spawn_agent(skills=["coder"])` or `load_skill("browser")` instead.

**Root agent base tools**: `run_bash_cmd`, `remember`, `forget`, `describe_image`, `play_audio` + core tools (scratchpad, spawn_agent, load_skill, list_skills, custom tools).

### Files

| File | Change |
|------|--------|
| `agents/computron/agent.py` | Rewrite to skill-based prompt (use `computron_skills` as template) |
| `agents/_registry.py` | Simplify — one agent ("computron"), remove all others |
| `skills/goal_planner.py` | New — goal planner skill wrapping tools from `tasks/_tools.py` |
| `sdk/skills/_registry.py` | Register goal_planner skill |
| `agents/computron_skills/` | Delete (merged into computron) |
| `agents/coding/` | Delete (replaced by coder skill) |
| `agents/browser/` | Delete (replaced by browser skill) |
| `agents/desktop/` | Delete (replaced by desktop skill) |
| `agents/goal_planner/` | Delete (replaced by goal_planner skill) |
| `server/aiohttp_app.py` | Simplify `/api/agents` (single entry or remove) |
| `server/message_handler.py` | Simplify `_build_agent()` — no agent resolution needed |
| `sdk/tools/_agent_wrapper.py` | Keep utility, remove all existing usages |

### UI changes

- Remove agent selector dropdown from `ChatInput.jsx`
- Remove `selectedAgent` state and `/api/agents` fetch

---

## Phase 3: Goal system uses skills + profiles (not agent names)

### What changes

**Task model**: Replace `agent: str` with `skills: list[str]` and `profile: str | None`.

```python
class Task(BaseModel):
    id: str
    goal_id: str
    description: str
    instruction: str
    skills: list[str] = Field(default_factory=list)  # replaces agent: str
    profile: str | None = None
    agent_config: dict[str, Any] | None = None       # keep for custom overrides
    depends_on: list[str] = Field(default_factory=list)
    max_retries: int = 3
```

**TaskExecutor**: Build agents from skills instead of resolving by agent name. `AgentState(core_tools)` → load each skill → apply profile → build Agent.

**Goal planner skill prompt**: Updated to reference skills instead of agent names. Tasks specify `skills: ["browser"]` instead of `agent: "browser"`.

**`add_task()` tool**: Replace `agent` param with `skills` param. Validate against skill registry instead of `_TASK_AGENTS`.

**Migration**: Existing saved goals have `agent: str`. Add a migration shim that maps `agent` → `skills` on load:
- `"browser"` → `["browser"]`
- `"coder"` → `["coder"]`
- `"computron"` → `[]`

### Files

| File | Change |
|------|--------|
| `tasks/_models.py` | `agent` → `skills`, add `profile` |
| `tasks/_tools.py` | `agent` param → `skills` param, validate against skill registry |
| `tasks/_executor.py` | Build agent from skills + profile instead of agent registry |
| `tasks/_file_store.py` | Migration shim for old `agent` field on load |
| `skills/goal_planner.py` | Update prompt to reference skills |

---

## Implementation order

Phases 1 and 2 are mostly independent and could be done in parallel. Phase 3 depends on Phase 2.

**Phase 1** is lowest risk — additive, no breaking changes.
**Phase 2** is the biggest change — deletes agents, removes UI elements, creates goal_planner skill.
**Phase 3** depends on Phase 2 (no agent names to reference).

---

## Verification

After each phase:
- All existing tests pass (`just test`)
- UI builds clean (`just ui-build`)
- Manual test: start conversation, load skills, spawn sub-agents
- Goal creation and execution works end-to-end
- Existing saved goals still load (Phase 3 migration shim)
