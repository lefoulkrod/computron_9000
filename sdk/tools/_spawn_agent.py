"""Spawn isolated sub-agents with dynamically composed skills."""

import logging
import uuid as _uuid
from textwrap import dedent

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agents.types import Agent
from sdk.context import ContextManager, ConversationHistory, LLMCompactionStrategy, ToolClearingStrategy
from sdk.events import agent_span, get_current_agent_id, get_model_options
from sdk.hooks import default_hooks
from sdk.hooks._persistence import PersistenceHook
from sdk.turn import StopRequestedError, get_conversation_id, run_turn
logger = logging.getLogger(__name__)

_console = Console(stderr=True)


def _log_spawn(agent_name: str, profile_id: str | None, agent_profile, model_options, skills: list[str], instruction_preview: str) -> None:
    """Print a Rich panel when a sub-agent is spawned."""
    body = Text()
    body.append("agent:   ", style="bold")
    body.append(agent_name, style="bright_cyan")
    body.append("\nprofile: ", style="bold")
    body.append(profile_id or "(parent)", style="bright_magenta")
    body.append("\nmodel:   ", style="bold")
    body.append(model_options.model or "—", style="bright_yellow")
    if skills:
        body.append("\nskills:  ", style="bold")
        body.append(", ".join(skills), style="bright_cyan")
    # Show non-default inference params
    params = []
    if model_options.temperature is not None:
        params.append(f"temp={model_options.temperature}")
    if model_options.top_k is not None:
        params.append(f"top_k={model_options.top_k}")
    if model_options.top_p is not None:
        params.append(f"top_p={model_options.top_p}")
    if model_options.think:
        params.append("think")
    if model_options.num_ctx is not None:
        params.append(f"ctx={model_options.num_ctx}")
    if model_options.max_iterations is not None:
        params.append(f"max_iter={model_options.max_iterations}")
    if params:
        body.append("\nparams:  ", style="bold")
        body.append(", ".join(params), style="dim")
    body.append("\ntask:    ", style="bold")
    preview = instruction_preview[:150]
    if len(instruction_preview) > 150:
        preview += "…"
    body.append(preview, style="dim")

    _console.print(Panel(
        body,
        title="[bold bright_cyan]🚀 Spawn Agent[/bold bright_cyan]",
        border_style="bright_cyan",
        expand=False,
    ))


def _log_spawn_complete(agent_name: str, result_preview: str) -> None:
    """Print a Rich panel when a spawned agent completes."""
    body = Text()
    body.append("agent:  ", style="bold")
    body.append(agent_name, style="green")
    body.append("\nresult: ", style="bold")
    preview = result_preview[:200]
    if len(result_preview) > 200:
        preview += "…"
    body.append(preview, style="green")

    _console.print(Panel(
        body,
        title="[bold green]✅ Agent Complete[/bold green]",
        border_style="green",
        expand=False,
    ))


def _log_spawn_error(agent_name: str, error: str) -> None:
    """Print a Rich panel when a spawned agent fails."""
    body = Text()
    body.append("agent: ", style="bold")
    body.append(agent_name, style="red")
    body.append("\nerror: ", style="bold")
    body.append(error, style="red")

    _console.print(Panel(
        body,
        title="[bold red]❌ Agent Error[/bold red]",
        border_style="red",
        expand=False,
    ))

_BASE_PROMPT = dedent("""\
    You are a worker sub-agent. Complete your task thoroughly.

    Use save_to_scratchpad to store important results for other agents.
    Scratchpad entries persist for the entire conversation and are shared
    across all agents. Earlier tool results may be cleared from context,
    so the scratchpad is the reliable way to keep important data available.

    Verify correctness, retry on failure.
    Return a concise summary with all file paths when done.
""")


async def spawn_agent(
    instructions: str,
    agent_name: str = "SUB_AGENT",
    profile: str | None = None,
) -> str:
    """Spawn a sub-agent to handle a task in isolation.

    The sub-agent runs in its own context window. Use this for tasks that
    are long-running or produce large intermediate output (long browsing
    sessions, multi-file code generation) so they don't consume the
    parent's context.

    Call list_agent_profiles() to see available profiles.

    Args:
        instructions: Complete, self-contained task description. Include
            EVERYTHING the agent needs — it has zero context from the parent.
        agent_name: Short UPPERCASE name for the UI (e.g. DATA_ANALYST).
        profile: Agent profile ID (e.g. "code_expert", "research_agent").
            Determines the model, skills, system prompt, and inference
            parameters. Omit to use the parent agent's settings.

    Returns:
        Summary of what the sub-agent accomplished.
    """
    from agents._agent_profiles import AgentProfile, build_llm_options, get_agent_profile
    from sdk.skills.agent_state import AgentState

    from sdk.tools._core import get_core_tools

    # Resolve profile. Unknown or disabled IDs return a clear error string
    # so the caller can pick a valid one instead of silently getting the
    # parent's options.
    agent_profile: AgentProfile | None = None
    if profile:
        agent_profile = get_agent_profile(profile)
        if agent_profile is None:
            msg = (
                f"Agent profile '{profile}' not found. "
                "Call list_agent_profiles() to see available profiles."
            )
            _log_spawn_error(agent_name, msg)
            return msg
        if not agent_profile.enabled:
            msg = (
                f"Agent profile '{profile}' is disabled and cannot be used "
                "by spawn_agent. Call list_agent_profiles() to see available profiles."
            )
            _log_spawn_error(agent_name, msg)
            return msg

    if agent_profile:
        model_options = build_llm_options(agent_profile)
        system_prompt = agent_profile.system_prompt or _BASE_PROMPT
        skills = list(agent_profile.skills)
    else:
        model_options = get_model_options()
        system_prompt = _BASE_PROMPT
        skills = []

    loaded = AgentState(get_core_tools())
    for skill_name in skills:
        if loaded.load(skill_name) is None:
            _log_spawn_error(agent_name, f"Unknown skill: {skill_name}")
            return f"Unknown skill: {skill_name}"

    effective_max_iterations = 0
    if model_options and model_options.max_iterations is not None:
        effective_max_iterations = model_options.max_iterations

    agent = Agent(
        name=agent_name,
        description="",
        instruction=system_prompt,
        tools=loaded.tools,
        model=model_options.model if model_options and model_options.model else "",
        think=model_options.think if model_options and model_options.think is not None else False,
        options=model_options.to_options() if model_options else {},
        max_iterations=effective_max_iterations,
    )

    logger.info(
        "Spawning sub-agent '%s' (profile=%s, max_iter=%d, instruction=%.100s)",
        agent_name, profile or "(parent)", effective_max_iterations, instructions,
    )
    _log_spawn(agent_name, profile, agent_profile, model_options, skills, instructions)

    _profile_name = agent_profile.name if agent_profile else None
    async with agent_span(agent_name, instruction=instructions, agent_state=loaded, profile_name=_profile_name):
        conv_id = get_conversation_id() or "default"
        short_id = _uuid.uuid4().hex[:8]
        instance_id = f"{conv_id}/{agent_name}_{short_id}"
        history = ConversationHistory(
            [
                {"role": "system", "content": agent.instruction},
                {"role": "user", "content": instructions},
            ],
            instance_id=instance_id,
        )

        num_ctx = agent.options.get("num_ctx", 0) if agent.options else 0
        ctx_manager = ContextManager(
            history=history,
            context_limit=num_ctx,
            agent_name=agent.name,
            strategies=[ToolClearingStrategy(), LLMCompactionStrategy()],
        )
        hooks = default_hooks(
            agent,
            max_iterations=effective_max_iterations,
            ctx_manager=ctx_manager,
        )
        hooks.append(PersistenceHook(
            conversation_id=conv_id,
            history=history,
            sub_agent_name=agent_name,
            sub_agent_id=short_id,
        ))

        try:
            result_text = await run_turn(
                history=history,
                agent=agent,
                hooks=hooks,
            )
        except StopRequestedError:
            logger.info("Spawned agent '%s' stopped by user request", agent_name)
            raise
        except Exception as exc:
            _log_spawn_error(agent_name, str(exc))
            logger.exception("Unexpected error in spawned agent '%s'", agent_name)
            raise

    result = (result_text or "").strip()
    _log_spawn_complete(agent_name, result)
    return result
