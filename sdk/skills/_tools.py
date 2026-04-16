"""The load_skill and list_available_skills meta-tools."""

import logging

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ._registry import get_skill, list_skills
from .agent_state import get_active_agent_state

logger = logging.getLogger(__name__)

_console = Console(stderr=True)


def _log_skill_loaded(skill_name: str, description: str, new_tools: list[str]) -> None:
    """Print a Rich panel when a skill is loaded."""
    body = Text()
    body.append("skill: ", style="bold")
    body.append(skill_name, style="bright_magenta")
    body.append(f"  ({description})", style="dim")
    if new_tools:
        body.append(f"\ntools: ", style="bold")
        body.append(", ".join(new_tools), style="bright_magenta")
    else:
        body.append("\ntools: ", style="bold")
        body.append("(none — guidance only)", style="dim")

    _console.print(Panel(
        body,
        title="[bold bright_magenta]⚡ Skill Loaded[/bold bright_magenta]",
        border_style="bright_magenta",
        expand=False,
    ))


def _log_skill_already_loaded(skill_name: str) -> None:
    """Print a dim panel when a skill is requested but already loaded."""
    body = Text()
    body.append(skill_name, style="bright_magenta")
    body.append("  (already loaded)", style="dim")

    _console.print(Panel(
        body,
        title="[bold dim]⚡ Skill[/bold dim]",
        border_style="dim",
        expand=False,
    ))


def _log_skill_error(skill_name: str, error: str) -> None:
    """Print a red panel when a skill load fails."""
    body = Text()
    body.append("skill: ", style="bold")
    body.append(skill_name, style="red")
    body.append(f"\nerror: ", style="bold")
    body.append(error, style="red")

    _console.print(Panel(
        body,
        title="[bold red]⚡ Skill Error[/bold red]",
        border_style="red",
        expand=False,
    ))


def list_available_skills() -> str:
    """List all available skills that can be loaded with load_skill.

    Returns:
        A formatted list of skill names and descriptions.
    """
    entries = list_skills()
    if not entries:
        return "No skills available."
    lines = [f"  - {name}: {desc}" for name, desc in entries]
    return "Available skills:\n" + "\n".join(lines)


async def load_skill(name: str) -> str:
    """Load a skill to gain its tools and capabilities.

    Call list_available_skills() first to see what is available.
    Already-loaded skills return instantly without duplication.

    Args:
        name: Skill name from the catalog.

    Returns:
        Confirmation message, or an error message.
    """
    agent_state = get_active_agent_state()
    if agent_state is None:
        return "Error: no active skill scope (internal error)"

    if name in agent_state.loaded_skill_names:
        _log_skill_already_loaded(name)
        return f"Skill '{name}' is already loaded."

    skill = get_skill(name)
    if skill is None:
        available = ", ".join(n for n, _ in list_skills())
        error_msg = f"Unknown skill '{name}'. Available: {available}"
        _log_skill_error(name, error_msg)
        return error_msg

    agent_state.add(skill)
    skill_tools = [getattr(t, "__name__", "?") for t in skill.tools]
    _log_skill_loaded(name, skill.description, skill_tools)
    return f"Loaded skill '{name}' ({len(skill_tools)} tools). Instructions added to system prompt."
