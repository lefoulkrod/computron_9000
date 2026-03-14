"""ScratchpadHook — logs Rich panels when the agent reads or writes the scratchpad."""

from __future__ import annotations

import json
import logging
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

logger = logging.getLogger(__name__)

_SCRATCHPAD_TOOLS = frozenset({"save_to_scratchpad", "recall_from_scratchpad"})


class ScratchpadHook:
    """Displays a Rich panel whenever the agent uses a scratchpad tool."""

    def __init__(self) -> None:
        self._console = Console(stderr=True)

    def after_tool(
        self, tool_name: str | None, tool_arguments: dict[str, Any], tool_result: str
    ) -> str:
        """Log a panel for scratchpad reads and writes."""
        if tool_name not in _SCRATCHPAD_TOOLS:
            return tool_result

        # Try to parse the result for structured display
        try:
            result_data = json.loads(tool_result.replace("'", '"'))
        except (json.JSONDecodeError, ValueError):
            result_data = None

        if tool_name == "save_to_scratchpad":
            key = tool_arguments.get("key", "?")
            value = tool_arguments.get("value", "")
            if len(value) > 200:
                value = value[:200] + "…"

            body = Text()
            body.append("key:   ", style="bold")
            body.append(key, style="green")
            body.append("\nvalue: ", style="bold")
            body.append(value, style="green")

            self._console.print(Panel(
                body,
                title="[bold green]📝 Scratchpad Write[/bold green]",
                border_style="green",
                expand=False,
            ))

        elif tool_name == "recall_from_scratchpad":
            key = tool_arguments.get("key")
            body = Text()

            if result_data and result_data.get("status") == "ok":
                if "items" in result_data:
                    # Recall all
                    items = result_data["items"]
                    if items:
                        body.append(f"({len(items)} item{'s' if len(items) != 1 else ''})\n", style="dim")
                        for k, v in items.items():
                            v_str = str(v)
                            if len(v_str) > 120:
                                v_str = v_str[:120] + "…"
                            body.append(f"  {k}: ", style="bold")
                            body.append(v_str + "\n", style="cyan")
                    else:
                        body.append("(empty — no items stored)", style="dim")
                else:
                    # Single key recall
                    value = str(result_data.get("value", ""))
                    if len(value) > 200:
                        value = value[:200] + "…"
                    body.append("key:   ", style="bold")
                    body.append(str(key), style="cyan")
                    body.append("\nvalue: ", style="bold")
                    body.append(value, style="cyan")
            elif result_data and result_data.get("status") == "not_found":
                body.append("key:   ", style="bold")
                body.append(str(key), style="red")
                body.append("\n(not found)", style="dim red")
            else:
                body.append(tool_result)

            self._console.print(Panel(
                body,
                title="[bold cyan]🔍 Scratchpad Read[/bold cyan]",
                border_style="cyan",
                expand=False,
            ))

        return tool_result
