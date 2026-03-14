"""LoggingHook — logs model inputs and outputs using Rich panels and tables."""

from __future__ import annotations

import json
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

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
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

    async def after_model(
        self, response: Any, history: Any, iteration: int, agent_name: str
    ) -> Any:
        """Log the model response and runtime stats."""
        if not logger.isEnabledFor(logging.DEBUG):
            return response

        # Build stats table if available (check raw for Ollama-specific timing)
        stats_table = None
        raw = getattr(response, "raw", None)
        if raw is not None and hasattr(raw, "done") and getattr(raw, "done", False):
            from sdk.providers import llm_runtime_stats

            stats = llm_runtime_stats(raw)
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
        thinking_text = ""
        content_text = ""
        tool_calls_text = ""
        if hasattr(response, "message"):
            msg = response.message
            if hasattr(msg, "thinking") and msg.thinking:
                thinking = msg.thinking
                if len(thinking) > 200:
                    thinking = thinking[:200] + "…"
                thinking_text = thinking
            if hasattr(msg, "content") and msg.content:
                content = msg.content
                if len(content) > 500:
                    content = content[:500] + "..."
                content_text = content
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_calls_parts = []
                for tc in msg.tool_calls:
                    func = getattr(tc, "function", tc)
                    name = getattr(func, "name", "?")
                    args = getattr(func, "arguments", None) or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            args = {"_raw": args}
                    arg_parts = []
                    for k, v in args.items():
                        v_str = str(v)
                        if len(v_str) > 120:
                            v_str = v_str[:120] + "…"
                        arg_parts.append(f"{k}={v_str}")
                    tool_calls_parts.append(
                        f"{name}({', '.join(arg_parts)})"
                    )
                tool_calls_text = "\n".join(tool_calls_parts)

        # Compose output
        parts = []
        if stats_table:
            parts.append(stats_table)
        if thinking_text:
            label = Text("Thinking: ", style="bold dim")
            label.append(thinking_text, style="dim")
            parts.append(label)
        if content_text:
            label = Text("Response: ", style="bold")
            label.append(content_text)
            parts.append(label)
        if tool_calls_text:
            label = Text("Tool calls:\n", style="bold magenta")
            label.append(tool_calls_text, style="magenta")
            parts.append(label)

        self._console.print(Panel(
            Group(*parts) if parts else Text("(empty response)", style="dim"),
            title=f"[bold yellow]{self._agent_name}[/bold yellow]  after_model  iteration {iteration}",
            border_style="yellow",
            expand=False,
        ))
        return response
