"""LoggingHook — logs model inputs and outputs using Rich panels and tables."""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)


class LoggingHook:
    """Logs model inputs and outputs using Rich panels and tables."""

    def __init__(self, agent: Any) -> None:
        """Initialize with the agent whose name is used in log lines."""
        self._agent_name: str = getattr(agent, "name", "unknown")
        self._console = Console(stderr=True)

    def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Log the chat history being sent to the model."""
        if not logger.isEnabledFor(logging.DEBUG):
            return
        msg_count = len(history.messages)
        roles = {}
        for msg in history.messages:
            role = msg.get("role", "unknown")
            roles[role] = roles.get(role, 0) + 1
        role_summary = "  ".join(f"{r}: {c}" for r, c in sorted(roles.items()))

        self._console.print(Panel(
            f"[bold]{msg_count}[/bold] messages  ({role_summary})",
            title=f"[bold cyan]{self._agent_name}[/bold cyan]  before_model  iteration {iteration}",
            border_style="cyan",
            expand=False,
        ))

    def after_model(
        self, response: Any, history: Any, iteration: int, agent_name: str
    ) -> Any:
        """Log the model response and runtime stats."""
        if not logger.isEnabledFor(logging.DEBUG):
            return response

        # Build stats table if available
        stats_table = None
        if hasattr(response, "done") and getattr(response, "done", False):
            from agents.ollama.sdk.llm_runtime_stats import llm_runtime_stats

            stats = llm_runtime_stats(response)
            stats_table = Table(show_header=False, expand=False, padding=(0, 1))
            stats_table.add_column("Metric", style="bold")
            stats_table.add_column("Value", justify="right")

            total = getattr(stats, "total_duration", 0) or 0
            load = getattr(stats, "load_duration", 0) or 0
            prompt_count = getattr(stats, "prompt_eval_count", 0) or 0
            prompt_dur = getattr(stats, "prompt_eval_duration", 0) or 0
            prompt_tps = getattr(stats, "prompt_tokens_per_sec", 0) or 0
            eval_count = getattr(stats, "eval_count", 0) or 0
            eval_dur = getattr(stats, "eval_duration", 0) or 0
            eval_tps = getattr(stats, "eval_tokens_per_sec", 0) or 0

            stats_table.add_row("Total duration", f"{total:.3f}s")
            stats_table.add_row("Model load", f"{load:.3f}s")
            stats_table.add_row("Prompt tokens", f"{prompt_count}  ({prompt_dur:.3f}s, {prompt_tps:.1f} tok/s)")
            stats_table.add_row("Eval tokens", f"{eval_count}  ({eval_dur:.3f}s, {eval_tps:.1f} tok/s)")

        # Extract response content summary
        content_text = ""
        tool_calls_text = ""
        if hasattr(response, "message"):
            msg = response.message
            if hasattr(msg, "content") and msg.content:
                content = msg.content
                if len(content) > 500:
                    content = content[:500] + "..."
                content_text = content
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                calls = []
                for tc in msg.tool_calls:
                    name = getattr(tc.function, "name", "?") if hasattr(tc, "function") else getattr(tc, "name", "?")
                    calls.append(name)
                tool_calls_text = ", ".join(calls)

        # Compose output
        parts = []
        if stats_table:
            parts.append(stats_table)
        if content_text:
            label = Text("Response: ", style="bold")
            label.append(content_text)
            parts.append(label)
        if tool_calls_text:
            label = Text("Tool calls: ", style="bold magenta")
            label.append(tool_calls_text, style="magenta")
            parts.append(label)

        self._console.print(Panel(
            Group(*parts) if parts else Text("(empty response)", style="dim"),
            title=f"[bold yellow]{self._agent_name}[/bold yellow]  after_model  iteration {iteration}",
            border_style="yellow",
            expand=False,
        ))
        return response
