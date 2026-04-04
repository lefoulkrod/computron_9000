# Progressive Skill & Tool Loading

Add a skill-based agent alongside the existing pre-defined agents. A new
`COMPUTRON_SKILLS` agent loads tools progressively and composes sub-agents
from skills dynamically. The existing `COMPUTRON_9000`, `BROWSER_AGENT`,
`COMPUTER_AGENT`, and `DESKTOP_AGENT` remain untouched so both approaches
can run side by side until the skill-based approach is proven.

## Goals

1. Reduce context waste — agents only carry tools they actually need.
2. Remove rigid agent boundaries — a single agent can combine browser + coder
   tools when the task requires it.
3. Flexible sub-agent spawning — `spawn_agent(instructions, skills=[...])`
   composes sub-agents from any combination of skills.
4. Make capabilities additive — new skill modules can be dropped in without
   touching existing agents or routing logic.
5. Keep existing agents working — no changes to `COMPUTRON_9000` or its
   sub-agents. Both systems coexist, selectable from the UI agent dropdown.

## Key concepts

- **Skill** — a bundle of tools + a prompt fragment. Equivalent to what a
  current agent module exports (NAME, DESCRIPTION, SYSTEM_PROMPT, TOOLS).
- **ToolSet** — a mutable tool collection that grows mid-turn when skills are
  loaded. Replaces the static `list[Callable]` in the turn loop.
- **load_skill(name)** — meta-tool that adds a skill's tools to the active
  ToolSet and returns instructions + tool docs.
- **spawn_agent(instructions, skills)** — spawns an isolated sub-agent with
  the requested skills pre-loaded.
- **COMPUTRON_SKILLS** — new root agent that uses `load_skill` + `spawn_agent`
  instead of hardcoded sub-agent wrappers. Lives alongside `COMPUTRON_9000`.

## Non-goals

- Changing the provider layer or tool schema generation.
- Changing the sub-agent isolation model (own history, own ContextManager).
- Modifying or removing existing agents.

---

## Step 1 — ToolSet + ContextVar

**What**: Introduce `ToolSet` as a mutable wrapper around the tool list, and a
ContextVar so tool functions can access it mid-turn.

**Files**:
- NEW `sdk/skills/__init__.py` — public re-exports
- NEW `sdk/skills/_tool_set.py` — `ToolSet` class + `_active_tool_set` ContextVar

**ToolSet API**:
```python
class ToolSet:
    def __init__(self, tools: list[Callable]) -> None: ...

    @property
    def tools(self) -> list[Callable]: ...

    @property
    def loaded_skills(self) -> frozenset[str]: ...

    def add(self, skill_name: str, tools: list[Callable]) -> list[str]:
        """Add tools from a skill. Deduplicates by __name__. Returns new names."""

    def find(self, name: str) -> Callable | None:
        """Look up a tool by function name."""
```

**ContextVar**:
```python
_active_tool_set: ContextVar[ToolSet | None] = ContextVar("_active_tool_set", default=None)

def get_active_tool_set() -> ToolSet | None: ...
```

**Why a ContextVar**: Follows the existing pattern in `sdk/events/_context.py`
(`_current_agent_name`, `_model_options`, `_context_stack`, etc.). Tool
functions can access the ToolSet without it being threaded through as a
parameter.

**Isolation via `agent_span`**: The ContextVar is scoped to agent spans to
prevent parent ToolSets from leaking into sub-agents. `agent_span` already
manages agent-level ContextVars (`_context_stack`). Adding ToolSet scoping
here means every `agent_span` entry resets the ToolSet to `None`, and exit
restores the parent's value — same pattern as the context stack:

```python
# In sdk/events/_context.py — agent_span additions:
@contextmanager
def agent_span(agent_name=None, instruction=None):
    stack = _context_stack.get()
    # ... existing setup ...
    token = _context_stack.set((*stack, (context_id, agent_name)))
    tool_set_token = _active_tool_set.set(None)     # reset for this scope

    try:
        yield context_id
    finally:
        # ... existing cleanup ...
        _context_stack.reset(token)
        _active_tool_set.reset(tool_set_token)       # restore parent's
```

This ensures:
1. Sub-agent enters `agent_span` → ToolSet reset to `None`
2. Sub-agent's `run_turn` → sets its own fresh ToolSet
3. Sub-agent exits `agent_span` → parent's ToolSet restored via `reset(token)`
4. No ToolSet leaks between concurrent sub-agents (each `asyncio.create_task`
   gets a context copy, and `agent_span` resets within that copy)

**Tests**: Unit tests for ToolSet — add, dedup, find, loaded_skills tracking.
Test that `agent_span` resets and restores the ToolSet ContextVar.

**Behavioral change**: None. ToolSet is created but nothing uses it yet.
`agent_span` resets a ContextVar that defaults to `None` anyway.

---

## Step 2 — Wire ToolSet into the turn loop

**What**: `run_turn` creates a ToolSet, sets the ContextVar, and uses
`tool_set.tools` instead of the local `tools` list.

**Files**:
- EDIT `sdk/turn/_execution.py`

**Changes to `run_turn`**:
```python
async def run_turn(history, agent, *, hooks=None) -> str | None:
    provider = get_provider()
    tool_set = ToolSet(agent.tools or [])
    token = _active_tool_set.set(tool_set)
    # ...
    try:
        while True:
            # Each iteration passes tool_set.tools to the provider.
            # If load_skill added tools between iterations, the provider
            # sees them on the next call — no schema caching to invalidate.
            async for chunk in _stream_chat_with_retries(
                provider, ..., tools=tool_set.tools, ...
            ):
                ...

            # Tool execution also uses tool_set.tools
            await _run_tool_with_hooks(tc, tool_set.tools, hooks)
    finally:
        _active_tool_set.reset(token)
        # ... on_turn_end hooks ...
```

**Why this works**: The provider already converts `tools` to JSON schemas on
every `chat_stream` call. There's no cached schema to bust. When `load_skill`
appends tools to `tool_set.tools` between iterations, the next provider call
automatically includes the new schemas.

**Interaction with `agent_span` scoping**: `run_turn` is always called inside
an `agent_span` (either in `message_handler._run_turn` or in
`_agent_wrapper.run_agent_as_tool` / `spawn_agent`). The `agent_span` resets
`_active_tool_set` to `None` on entry. Then `run_turn` sets it to the agent's
own `ToolSet`. On exit, `agent_span` restores the parent's value. This gives
clean scoping without `run_turn` needing to know about parent/child
relationships.

**Tests**: Existing turn loop tests should pass unchanged (ToolSet wraps the
same list). Add a test that mutates `tool_set` mid-turn and verifies the next
provider call sees the new tools.

**Behavioral change**: None yet — tool list is mutable but nothing mutates it.
All existing agents work identically.

---

## Step 3 — Skill model + registry

**What**: Define the `Skill` data model and a registry that skill modules
populate at import time.

**Files**:
- NEW `sdk/skills/_registry.py` — `Skill` model, `register_skill`, `get_skill`, `list_skills`

**Skill model**:
```python
class Skill(BaseModel):
    name: str
    description: str  # one line — shown in the catalog
    prompt: str       # injected into context when loaded
    tools: list[Callable[..., Any]]

    model_config = {"arbitrary_types_allowed": True}
```

**Registry API**:
```python
_SKILL_REGISTRY: dict[str, Skill] = {}

def register_skill(skill: Skill) -> None: ...
def get_skill(name: str) -> Skill | None: ...
def list_skills() -> list[tuple[str, str]]: ...
```

**Tests**: Register, retrieve, list, duplicate name handling.

**Behavioral change**: None — registry exists but nothing populates it yet.

---

## Step 4 — Skill modules (repackage current agents as skills)

**What**: Create skill modules that register current agent capabilities as
skills. The current agent modules are unchanged — skills reference the same
tool functions but register them independently.

**Files**:
- NEW `skills/__init__.py` — imports all skill modules to trigger registration
- NEW `skills/browser.py`
- NEW `skills/coder.py`
- NEW `skills/desktop.py`
- NEW `skills/media.py`

Each skill module follows this pattern:
```python
# skills/browser.py
from sdk.skills import Skill, register_skill
from tools.browser import open_url, browse_page, click, ...

_SKILL = Skill(
    name="browser",
    description="Web browsing, page interaction, form filling, screenshots",
    prompt=dedent("""..."""),  # adapted from BROWSER_AGENT SYSTEM_PROMPT
    tools=[open_url, browse_page, click, ...],
)
register_skill(_SKILL)
```

**Prompt content**: Adapted from the current agent SYSTEM_PROMPT constants.
The prompts should work as composable fragments — focused on tool usage
guidance, not agent identity (no "You are BROWSER_AGENT" preamble).

**Import timing**: `skills/__init__.py` imports all skill modules to trigger
registration. Add `import skills` in the application startup path (e.g.
`main.py` or `server/aiohttp_app.py`).

**Tests**: Verify each skill registers with the expected name, tool count,
and non-empty prompt.

**Behavioral change**: None — skills are registered but nothing loads them.
Existing agents are untouched.

---

## Step 5 — `load_skill` tool

**What**: The meta-tool that agents call to load a skill into their active
ToolSet mid-turn.

**Files**:
- NEW `sdk/skills/_loader.py` — `load_skill` async function

**Implementation**:
```python
async def load_skill(name: str) -> str:
    """Load a skill to gain its tools and capabilities.

    Args:
        name: Skill name from the available catalog.
    """
    tool_set = get_active_tool_set()
    if tool_set is None:
        return "Error: no active tool set"

    if name in tool_set.loaded_skills:
        return f"Skill '{name}' is already loaded."

    skill = get_skill(name)
    if skill is None:
        available = ", ".join(n for n, _ in list_skills())
        return f"Unknown skill '{name}'. Available: {available}"

    tool_set.add(name, skill.tools)
    return skill.prompt
```

**No tool docs in the return value**: The provider handles tool schema
injection automatically. The Ollama provider passes raw callables to the
Ollama client (which generates schemas internally). The Anthropic provider
converts via `callable_to_json_schema` on every `chat_stream` call. Either
way, once `load_skill` adds tools to the ToolSet, the next provider call
includes their schemas automatically. `load_skill` only needs to return the
skill's prompt fragment (usage instructions, workflow guidance, etc.).

**Docstring catalog**: The `load_skill` docstring should list available skills
so the LLM sees them in the tool schema. Build this dynamically at startup
after all skills are registered:

```python
def _finalize_load_skill_docstring() -> None:
    catalog = "\n".join(f"  - {n}: {d}" for n, d in list_skills())
    load_skill.__doc__ = load_skill.__doc__ + f"\n\nAvailable skills:\n{catalog}"
```

Call this after `import skills` in the startup path.

**Tests**:
- load_skill adds tools to ToolSet
- load_skill returns skill prompt
- Loading same skill twice is a no-op
- Unknown skill returns error with available list

**Behavioral change**: The tool exists but isn't wired into any agent yet.

---

## Step 6 — `spawn_agent` with dynamic skills

**What**: A new tool that spawns an isolated sub-agent with dynamically
composed skills. Coexists with the existing `run_sub_agent`,
`browser_agent_tool`, etc.

**Files**:
- NEW `sdk/tools/_spawn_agent.py` — `spawn_agent` function
- EDIT `sdk/tools/__init__.py` — re-export

**Implementation**:
```python
_CORE_TOOLS = [save_to_scratchpad, recall_from_scratchpad]

_BASE_PROMPT = dedent("""
    You are a worker sub-agent. Complete your task thoroughly.
    Use save_to_scratchpad to store important results for other agents.
    Verify correctness, retry on failure.
    Return a concise summary with all file paths when done.
""")

async def spawn_agent(
    instructions: str,
    skills: list[str],
    agent_name: str = "SUB_AGENT",
) -> str:
    """Spawn a sub-agent with specified skills to handle a task in isolation.

    The sub-agent runs in its own context window. Use this for tasks that
    are long-running or produce large intermediate output (browsing, code
    generation) so they don't consume the parent's context.

    Args:
        instructions: Complete, self-contained task description.
        skills: Skills to load (e.g. ["browser"], ["coder", "browser"]).
        agent_name: Short UPPERCASE name for the UI (e.g. DATA_ANALYST).
    """
    from sdk.skills import get_skill

    # Collect tools and prompts from requested skills
    all_tools = list(_CORE_TOOLS)
    prompt_parts = [_BASE_PROMPT]
    for skill_name in skills:
        skill = get_skill(skill_name)
        if skill is None:
            return f"Unknown skill: {skill_name}"
        all_tools.extend(skill.tools)
        prompt_parts.append(skill.prompt)

    # Build agent with composed tools + prompt
    model_options = get_model_options()
    effective_max_iterations = 0
    if model_options and model_options.max_iterations is not None:
        effective_max_iterations = model_options.max_iterations
    agent = Agent(
        name=agent_name,
        description="",
        instruction="\n\n".join(prompt_parts),
        tools=all_tools,
        model=model_options.model if model_options and model_options.model else "",
        think=model_options.think if model_options and model_options.think is not None else False,
        persist_thinking=model_options.persist_thinking if model_options and model_options.persist_thinking is not None else True,
        options=model_options.to_options() if model_options else {},
        max_iterations=effective_max_iterations,
    )

    # Same isolation pattern as current run_sub_agent
    with agent_span(agent_name, instruction=instructions):
        conv_id = get_conversation_id() or "default"
        short_id = uuid.uuid4().hex[:8]
        instance_id = f"{conv_id}/{agent_name}_{short_id}"
        history = ConversationHistory([
            {"role": "system", "content": agent.instruction},
            {"role": "user", "content": instructions},
        ], instance_id=instance_id)

        num_ctx = agent.options.get("num_ctx", 0) if agent.options else 0
        ctx_manager = ContextManager(
            history=history,
            context_limit=num_ctx,
            agent_name=agent.name,
            strategies=[ToolClearingStrategy(), LLMCompactionStrategy()],
        )
        hooks = default_hooks(agent, max_iterations=effective_max_iterations, ctx_manager=ctx_manager)
        hooks.append(PersistenceHook(
            conversation_id=conv_id, history=history,
            sub_agent_name=agent_name, sub_agent_id=short_id,
        ))

        try:
            result = await run_turn(history=history, agent=agent, hooks=hooks)
        except StopRequestedError:
            raise
        except Exception:
            logger.exception("Unexpected error in spawn_agent '%s'", agent_name)
            raise
        finally:
            agent_id = get_current_agent_id()
            if agent_id:
                try:
                    from tools.browser.core import release_agent_browser
                    await release_agent_browser(agent_id)
                except Exception:
                    logger.debug("No browser context to release for '%s'", agent_id)

    return (result or "").strip()
```

**Tests**:
- spawn_agent composes tools from multiple skills
- Unknown skill returns error
- Sub-agent runs in isolated history
- Browser context cleanup still works

**Behavioral change**: The tool exists but isn't used by any agent yet.

---

## Step 7 — COMPUTRON_SKILLS agent

**What**: Create a new root agent `COMPUTRON_SKILLS` that uses `load_skill`
and `spawn_agent` instead of the hardcoded sub-agent wrappers. Register it
in the agent registry alongside `COMPUTRON_9000`.

**Files**:
- NEW `agents/computron_skills/agent.py` — new agent definition
- NEW `agents/computron_skills/__init__.py` — re-exports
- EDIT `server/message_handler.py` — add to registry

**Agent definition** (`agents/computron_skills/agent.py`):
```python
from sdk.skills import load_skill
from sdk.tools import spawn_agent
from tools.generation import generate_media
from tools.custom_tools import create_custom_tool, lookup_custom_tools, run_custom_tool
from tools.memory import forget, remember
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.virtual_computer import output_file, play_audio, run_bash_cmd
from tools.virtual_computer.describe_image import describe_image

NAME = "COMPUTRON_SKILLS"
DESCRIPTION = (
    "Skill-based COMPUTRON that loads tools on demand and composes "
    "sub-agents from skill bundles."
)
SYSTEM_PROMPT = dedent("""
    You are COMPUTRON_SKILLS, an orchestrator that loads capabilities on
    demand and delegates complex tasks to sub-agents.

    SKILLS — load tools on demand or delegate to sub-agents:

    - load_skill(name) — adds tools to YOUR context. Use for quick tasks
      where you want direct control (e.g. load "browser" to open one URL,
      load "coder" to edit a single file).

    - spawn_agent(instructions, skills) — runs a sub-agent in its OWN
      context. Use for heavy tasks that produce lots of intermediate output
      (long browsing sessions, multi-file code generation). The sub-agent's
      tool calls and results don't consume your context.
      Sub-agents can combine multiple skills (e.g. skills=["browser", "coder"]).

    Available skills: browser, coder, desktop, media

    WHEN TO LOAD vs SPAWN:
    - Load when the task is quick and you want to see results directly
      (open one URL, read one file, run one command).
    - Spawn when the task will take many tool calls or produce large
      output (browse multiple pages, write a multi-file project,
      long research sessions).

    DELEGATION — sub-agents are stateless. They have ZERO context. Write
    each delegation prompt as a self-contained brief that includes
    EVERYTHING the agent needs. See COMPUTRON_9000 delegation rules.

    PLANNING — before delegating:
    1. Check for existing custom tools first (lookup_custom_tools).
    2. Break the task into concrete, ordered steps.
    3. Decide which steps to handle directly (load_skill) vs delegate
       (spawn_agent).

    IMAGE GENERATION — use generate_media directly. Do NOT delegate to
    sub-agents or load a skill for it.

    CUSTOM TOOLS — always prefer existing tools over new code.

    OUTPUT — call output_file(path) for every file you or a sub-agent
    creates. play_audio(path) plays audio in the browser.

    MEMORY — remember(key, value) / forget(key). Store user preferences.

    SCRATCHPAD — save_to_scratchpad(key, value) / recall_from_scratchpad(key).
    Use for session data and inter-agent communication. Shared across all
    agents. Earlier tool results may be cleared — the scratchpad is the
    reliable way to keep important data available.

    Respond in Markdown. Brief rationale before tool calls; short summary after.
""")
TOOLS = [
    # Skill loading
    load_skill,
    spawn_agent,
    # Direct tools (always available, no skill needed)
    run_bash_cmd,
    generate_media,
    describe_image,
    output_file,
    play_audio,
    # Custom tools
    create_custom_tool,
    lookup_custom_tools,
    run_custom_tool,
    # Memory
    remember,
    forget,
    # Scratchpad
    save_to_scratchpad,
    recall_from_scratchpad,
]
```

**Registry addition** (`server/message_handler.py`):
```python
from agents.computron_skills import (
    DESCRIPTION as _SKILLS_DESCRIPTION,
    NAME as _SKILLS_NAME,
    SYSTEM_PROMPT as _SKILLS_PROMPT,
    TOOLS as _SKILLS_TOOLS,
)

_AGENT_REGISTRY: dict[str, tuple[str, str, str, list]] = {
    "computron": (...),       # unchanged
    "computron_skills": (_SKILLS_NAME, _SKILLS_DESCRIPTION, _SKILLS_PROMPT, _SKILLS_TOOLS),
    "browser": (...),         # unchanged
    "coder": (...),           # unchanged
    "desktop": (...),         # unchanged
}
```

**UI**: The agent dropdown gains a "computron_skills" option. No frontend
changes needed — `AVAILABLE_AGENTS` is computed from the registry keys.

**Tests**:
- COMPUTRON_SKILLS agent builds successfully
- load_skill works within a COMPUTRON_SKILLS turn
- spawn_agent works within a COMPUTRON_SKILLS turn
- Existing agents still work identically

**Behavioral change**: Users can select `computron_skills` from the UI to
try the skill-based approach. Selecting `computron` still uses the original
hardcoded agent. Both coexist.

---

## Step 8 — Integration testing and comparison

**What**: Run the same tasks through both `computron` and `computron_skills`
to compare quality, token usage, and latency.

**Things to evaluate**:
- Does the model reliably call `load_skill` when it needs to?
- Does the model choose `load_skill` vs `spawn_agent` appropriately?
- How much context does the skill-based approach save?
- Are there tasks where the hardcoded agents perform better?
- How do different Ollama models handle the meta-reasoning?

**Test scenarios**:
1. Simple question (no tools needed) — both agents should just answer
2. Single-skill task ("open this URL and tell me what's on it") —
   COMPUTRON_SKILLS should load_skill("browser") or spawn browser
3. Multi-skill task ("find flights and make a spreadsheet") —
   COMPUTRON_SKILLS should spawn with mixed skills
4. Complex multi-step task — compare delegation quality

**No code changes in this step** — this is evaluation work.

---

## Step 9 — Iterate based on findings

Possible outcomes:
- **Skills approach works well** → consider making it the default, eventually
  deprecate the old agents (separate future plan).
- **Works for some models, not others** → keep both, document which models
  work best with each approach.
- **Needs refinement** → adjust skill prompts, catalog format, load_skill
  docstring, spawn_agent API based on what the models struggle with.

The existing agents remain available regardless of outcome.

---

## Risk notes

- **Model quality**: Smaller Ollama models may struggle with the meta-reasoning
  of "which skill do I need?". Mitigate with a clear catalog in the `load_skill`
  docstring and good system prompt guidance. The existing agents provide a
  fallback when models can't handle skill selection.

- **Extra round-trip**: `load_skill` costs one LLM iteration before the model
  can use the loaded tools. For quick tasks this adds latency vs the hardcoded
  agents where tools are immediately available.

- **Prompt fragment composition**: When `spawn_agent` composes multiple skills,
  their prompt fragments concatenate. May need tuning if prompts conflict or
  become too long. Keep skill prompts focused on tool usage, not agent identity.

- **No risk to existing agents**: All changes are additive. The existing
  `COMPUTRON_9000` and its sub-agents are completely untouched.
