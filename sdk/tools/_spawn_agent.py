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


def _log_spawn(agent_name: str, skills: list[str], instruction_preview: str) -> None:
    """Print a Rich panel when a sub-agent is spawned."""
    body = Text()
    body.append("agent:  ", style="bold")
    body.append(agent_name, style="bright_cyan")
    body.append("\nskills: ", style="bold")
    body.append(", ".join(skills) if skills else "(none)", style="bright_cyan")
    body.append("\ntask:   ", style="bold")
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
    skills: list[str],
    agent_name: str = "SUB_AGENT",
    profile: str | None = None,
) -> str:
    """Spawn a sub-agent with specified skills to handle a task in isolation.

    The sub-agent runs in its own context window. Use this for tasks that
    are long-running or produce large intermediate output (browsing, code
    generation) so they don't consume the parent's context.

    Args:
        instructions: Complete, self-contained task description. Include
            EVERYTHING the agent needs — it has zero context from the parent.
        skills: Skills to load for this agent (e.g. ["browser"], ["coder", "browser"]).
        agent_name: Short UPPERCASE name for the UI (e.g. DATA_ANALYST).
        profile: Optional inference profile ID (e.g. "code", "creative") to
            tune temperature, top_k, and other inference parameters.

    Returns:
        Summary of what the sub-agent accomplished.
    """
    from agents._profiles import apply_profile, get_profile
    from sdk.skills.agent_state import AgentState

    from sdk.tools._core import get_core_tools

    loaded = AgentState(get_core_tools())
    for skill_name in skills:
        if loaded.load(skill_name) is None:
            _log_spawn_error(agent_name, f"Unknown skill: {skill_name}")
            return f"Unknown skill: {skill_name}"

    model_options = get_model_options()

    # Apply inference profile as defaults under per-request options
    if profile and model_options:
        resolved_profile = get_profile(profile)
        if resolved_profile:
            model_options = apply_profile(resolved_profile, model_options)
        else:
            logger.warning("Unknown profile '%s', ignoring", profile)

    effective_max_iterations = 0
    if model_options and model_options.max_iterations is not None:
        effective_max_iterations = model_options.max_iterations

    agent = Agent(
        name=agent_name,
        description="",
        instruction=_BASE_PROMPT,
        tools=loaded.tools,
        model=model_options.model if model_options and model_options.model else "",
        think=model_options.think if model_options and model_options.think is not None else False,
        persist_thinking=model_options.persist_thinking if model_options and model_options.persist_thinking is not None else True,
        options=model_options.to_options() if model_options else {},
        max_iterations=effective_max_iterations,
    )

    logger.info(
        "Spawning sub-agent '%s' (skills=%s, max_iter=%d, instruction=%.100s)",
        agent_name, skills, effective_max_iterations, instructions,
    )
    _log_spawn(agent_name, skills, instructions)

    async with agent_span(agent_name, instruction=instructions, agent_state=loaded):
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
