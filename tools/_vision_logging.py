"""Shared Rich panel logging for vision model tool calls."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Lazy-initialised Rich console for panel logging.
_console = None


def _get_console():
    global _console  # noqa: PLW0603
    if _console is None:
        from rich.console import Console
        _console = Console(stderr=True)
    return _console


def log_vision_panel(
    tool_name: str,
    model: str,
    prompt: str,
    response: str,
    elapsed_ms: float,
    *,
    image_source: str = "",
) -> None:
    """Emit a Rich panel summarising a vision model call.

    Only emits when DEBUG logging is enabled.

    Args:
        tool_name: Name of the tool (e.g. "describe_screen", "inspect_page").
        model: Vision model identifier.
        prompt: The prompt sent to the model.
        response: The model's text response.
        elapsed_ms: Wall-clock time in milliseconds.
        image_source: Optional label for the image origin (URL, path, etc.).
    """
    if not logger.isEnabledFor(logging.DEBUG):
        return

    from rich.panel import Panel
    from rich.text import Text

    body = Text()

    if image_source:
        body.append("SOURCE: ", style="bold blue")
        body.append(image_source + "\n\n")

    body.append("PROMPT:\n", style="bold yellow")
    body.append(prompt)
    body.append("\n\nRESPONSE:\n", style="bold green")
    body.append(response)

    title = "[bold cyan]%s[/bold cyan]  [dim]%s[/dim]" % (tool_name, model)
    subtitle = "[bold]%.0fms[/bold]  %d chars" % (elapsed_ms, len(response))

    _get_console().print(Panel(
        body,
        title=title,
        subtitle=subtitle,
        border_style="dim",
        expand=False,
    ))
