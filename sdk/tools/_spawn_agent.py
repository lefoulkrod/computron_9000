"""Spawn isolated sub-agents with dynamically composed skills."""

import logging
import uuid as _uuid

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agents import AgentProfile, build_agent, get_agent_profile
from sdk.context import ContextManager, ConversationHistory, LLMCompactionStrategy, ToolClearingStrategy
from sdk.events import agent_span
from sdk.hooks import PersistenceHook, default_hooks
from sdk.skills import AgentState, get_skill, list_skills
from sdk.tools._core import get_core_tools
from sdk.turn import StopRequestedError, get_conversation_id, run_turn

logger = logging.getLogger(__name__)

_console = Console(stderr=True)


def _log_spawn(agent_name: str, profile: AgentProfile, instruction_preview: str) -> None:
    """Print a Rich panel when a sub-agent is spawned."""
    body = Text()
    body.append("agent:   ", style="bold")
    body.append(agent_name, style="bright_cyan")
    body.append("\nprofile: ", style="bold")
    body.append(profile.id, style="bright_magenta")
    body.append("\nmodel:   ", style="bold")
    body.append(profile.model or "—", style="bright_yellow")
    if profile.skills:
        body.append("\nskills:  ", style="bold")
        body.append(", ".join(profile.skills), style="bright_cyan")
    params = []
    if profile.temperature is not None:
        params.append(f"temp={profile.temperature}")
    if profile.top_k is not None:
        params.append(f"top_k={profile.top_k}")
    if profile.top_p is not None:
        params.append(f"top_p={profile.top_p}")
    if profile.think:
        params.append("think")
    if profile.num_ctx is not None:
        params.append(f"ctx={profile.num_ctx}")
    if profile.max_iterations is not None:
        params.append(f"max_iter={profile.max_iterations}")
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

async def spawn_agent(
    instructions: str,
    profile: str,
    agent_name: str = "SUB_AGENT",
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
        profile: Agent profile ID (e.g. "code_expert", "research_agent").
            Determines the model, skills, system prompt, and inference
            parameters.
        agent_name: Short UPPERCASE name for the UI (e.g. DATA_ANALYST).

    Returns:
        Summary of what the sub-agent accomplished.
    """
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

    agent_state = AgentState(await get_core_tools())
    for skill_name in agent_profile.skills:
        skill = get_skill(skill_name)
        if skill is None:
            available = [n for n, _ in list_skills()]
            msg = (
                f"Profile '{profile}' references skill '{skill_name}', which is "
                f"not registered. Available skills: {available}."
            )
            _log_spawn_error(agent_name, msg)
            return msg
        agent_state.add(skill)

    agent = build_agent(agent_profile, tools=agent_state.tools, name=agent_name)

    logger.info(
        "Spawning sub-agent '%s' (profile=%s, max_iter=%d, instruction=%.100s)",
        agent_name, profile, agent.max_iterations, instructions,
    )
    _log_spawn(agent_name, agent_profile, instructions)

    async with agent_span(
        agent_name,
        instruction=instructions,
        agent_state=agent_state,
        profile_name=agent_profile.name,
    ):
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
            max_iterations=agent.max_iterations,
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
