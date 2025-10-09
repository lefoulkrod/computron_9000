"""Interactive REPL for executing individual browser tools.

This REPL exposes each public browser tool (open_url, current_page, click, drag, fill_field,
scroll_page, press_keys, extract_text, ask_about_screenshot, ground_elements_by_text,
close_browser) via a numbered menu. Selecting a tool will prompt for its arguments
and execute it against the shared persistent Playwright browser. Results are logged
in structured form. On exit (command /exit or EOF/KeyboardInterrupt) the shared
browser is closed via tools.browser.close_browser.

The full tool menu is reprinted every loop so the available options are always
visible without requiring a separate /help command (which still works).

Usage:
    uv run python -m repls.browser_tools_repl [--log-level DEBUG] [--all-logs]

Design notes:
    * Dynamic tool registry drives prompts & arg parsing.
    * Simple per-arg input parsing with JSON first (so lists/dicts can be passed) falling
      back to raw string. Empty input for optional args uses default.
    * All tool functions are awaited (they are async) and their return values logged.
    * Exceptions are caught and logged with context; loop continues.
    * Clean browser shutdown on exit.
    * Optional CLI flags:
        --log-level LEVEL   Set REPL logger verbosity (default INFO)
        --all-logs          Propagate REPL logs so other application loggers emit

Limitations:
    * Vision tools require configured vision model; failures are surfaced but not fatal.
    * This is a developer convenience REPL and is excluded from mypy checks (repls/ excluded).
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, get_origin, get_args, get_type_hints

from logging_config import setup_logging
from repls.repl_logging import get_repl_logger
from tools.browser import (
    ask_about_screenshot,
    list_clickable_elements,
    click,
    drag,
    close_browser,
    current_page,
    extract_text,
    fill_field,
    ground_elements_by_text,
    open_url,
    press_keys,
    scroll_page,
)
from tools.browser.core.exceptions import BrowserToolError

logger = get_repl_logger("browser_tools")

ToolFn = Callable[..., Coroutine[Any, Any, Any]]


class _ToolSpec:
    """Internal descriptor for a browser tool's callable and parameter metadata."""

    def __init__(self, name: str, func: ToolFn, description: str | None = None) -> None:
        self.name = name
        self.func = func
        self.description = description or ""
        # Introspect parameters (skip *args/**kwargs for clarity)
        sig = inspect.signature(func)
        params: list[inspect.Parameter] = []
        for p in sig.parameters.values():
            if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            # skip self / cls just in case (should not appear for module-level funcs)
            if p.name in {"self", "cls"}:
                continue
            params.append(p)
        self.params = params

    def prompt_for_args(self) -> dict[str, Any]:
        """Interactively collect arguments for this tool.

        For each parameter, display name, kind and default. Attempt to parse
        input as JSON; on failure treat as raw string. Empty input for a param
        with a default keeps that default. For required params, reprompt until
        non-empty.
        """
        collected: dict[str, Any] = {}
        for p in self.params:
            while True:
                default_marker = "" if p.default is inspect._empty else f" [default={p.default!r}]"
                prompt = f"Enter value for {p.name}{default_marker}: "
                raw = input(prompt).strip()
                if not raw:
                    # Use default if available
                    if p.default is not inspect._empty:
                        collected[p.name] = p.default
                        break
                    # Required param - reprompt
                    print("Value required.")
                    continue
                # Try JSON first for structured or typed values. If JSON parsing
                # fails we fall back to the raw string. Additionally, coerce
                # simple string inputs into lists when the parameter annotation
                # expects a list (for example: press_keys expects list[str]).
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError:
                    value = raw
                # Coerce plain string to single-item list when annotation is list[str]
                try:
                    # Resolve forward/quoted annotations (PEP 563) where possible so
                    # we can reliably detect list[str] even when annotations are
                    # stored as strings. Fall back to the raw parameter
                    # annotation if resolution fails.
                    try:
                        resolved = get_type_hints(self.func)
                        ann = resolved.get(p.name, p.annotation)
                    except Exception:
                        ann = p.annotation
                    expects_list_of_str = False
                    origin = get_origin(ann)
                    args = get_args(ann)
                    logger.debug(
                        "prompt_for_args: param=%s annotation=%r origin=%r args=%r value=%r",
                        p.name,
                        ann,
                        origin,
                        args,
                        value,
                    )
                    # If annotation is list or List[...] and either no inner type
                    # is provided or the inner type is `str`, treat as list[str].
                    if origin is list or ann is list:
                        if not args or args[0] is str:
                            expects_list_of_str = True
                    if expects_list_of_str and isinstance(value, str):
                        # Accept several common user inputs: 'Enter', '[Enter]', 'Enter,Tab'
                        trimmed = value.strip()
                        if trimmed.startswith("[") and trimmed.endswith("]"):
                            # Try to parse inner content as JSON list; fallback to splitting
                            try:
                                inner = json.loads(trimmed)
                                if isinstance(inner, list):
                                    value = inner
                                else:
                                    value = [trimmed[1:-1]]
                            except json.JSONDecodeError:
                                inner = trimmed[1:-1]
                                parts = [p.strip() for p in inner.split(",") if p.strip()]
                                value = parts if parts else [inner]
                        elif "," in trimmed:
                            parts = [p.strip() for p in trimmed.split(",") if p.strip()]
                            value = parts
                        else:
                            value = [trimmed]
                    logger.debug("prompt_for_args: coerced param=%s -> %r (type=%s)", p.name, value, type(value))
                except Exception:
                    # Be conservative: on any unexpected inspection error, don't modify value
                    pass
                collected[p.name] = value
                break
        return collected

    async def run(self) -> Any:
        args = self.prompt_for_args()
        return await self.func(**args)


# Ordered registry of tools to expose
_TOOLS: list[_ToolSpec] = [
    _ToolSpec("open_url", open_url, "Navigate to a URL and snapshot the page."),
    _ToolSpec("current_page", current_page, "Snapshot the current page."),
    _ToolSpec("click", click, "Click an element by text or selector."),
    _ToolSpec("drag", drag, "Drag an element to a selector or offset."),
    _ToolSpec("fill_field", fill_field, "Fill an input/textarea field."),
    _ToolSpec("press_keys", press_keys, "Press one or more keys (JSON list)."),
    _ToolSpec("scroll_page", scroll_page, "Scroll the page (direction, optional amount)."),
    _ToolSpec("extract_text", extract_text, "Extract visible text for a selector or text."),
    _ToolSpec("ask_about_screenshot", ask_about_screenshot, "Ask vision model about a screenshot."),
    _ToolSpec("ground_elements_by_text", ground_elements_by_text, "Ground UI elements by description."),
    _ToolSpec(
        "list_clickable_elements",
        list_clickable_elements,
        "List clickable elements (anchors + heuristic clickables) with pagination/filtering.",
    ),
]

_EXIT_COMMANDS = {"/exit", "exit", "quit", ":q", ":qa"}
_HELP_COMMANDS = {"/help", "help", "?"}


async def _run_tool(spec: _ToolSpec) -> None:
    try:
        logger.info("Running tool %s", spec.name)
        result = await spec.run()
        logger.info("Result (%s): %s", spec.name, _format_result(result))
    except BrowserToolError as exc:
        logger.error("Tool %s failed: %s", spec.name, exc)
    except Exception as exc:  # pragma: no cover - robust interactive guard
        logger.exception("Unexpected error in tool %s", spec.name)
        logger.error("Unexpected error: %s", exc)


def _format_result(result: Any) -> str:
    if result is None:
        return "None"
    try:
        # Pydantic BaseModel or dataclass-like objects
        if hasattr(result, "model_dump"):
            return json.dumps(result.model_dump(), indent=2)
        if isinstance(result, list):
            return json.dumps(
                [r.model_dump() if hasattr(r, "model_dump") else r for r in result],
                indent=2,
            )
        # Handle dicts which may contain Pydantic models as values (for example
        # the updated scroll_page returns {"snapshot": PageSnapshot, "scroll": {...}}).
        if isinstance(result, dict):
            serializable = {}
            for k, v in result.items():
                if hasattr(v, "model_dump"):
                    serializable[k] = v.model_dump()
                else:
                    serializable[k] = v
            return json.dumps(serializable, indent=2)
        if isinstance(result, tuple):
            return json.dumps(list(result), indent=2)
        return str(result)
    except Exception:
        return str(result)


def _print_menu() -> None:
    print("\nAvailable Browser Tools:")
    for idx, spec in enumerate(_TOOLS, start=1):
        print(f"  {idx}) {spec.name} - {spec.description}")
    # Compact one-line summary for quick scanning
    names = ", ".join(spec.name for spec in _TOOLS)
    print(f"Tools: {names}")
    print("Commands: /exit to quit. Select by number or name.")


def _find_tool(selection: str) -> _ToolSpec | None:
    # numeric selection
    if selection.isdigit():
        idx = int(selection)
        if 1 <= idx <= len(_TOOLS):
            return _TOOLS[idx - 1]
    # name selection
    lowered = selection.lower()
    for spec in _TOOLS:
        if spec.name.lower() == lowered:
            return spec
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive browser tools REPL")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set REPL logger level (default INFO)",
    )
    # By default show all application logs in the REPL; provide a switch to disable.
    parser.add_argument(
        "--no-all-logs",
        dest="all_logs",
        action="store_false",
        help="Disable propagation to root loggers (use isolated REPL logging).",
    )
    parser.set_defaults(all_logs=True)
    return parser


async def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    setup_logging()
    # Reconfigure REPL logger per CLI flags (propagation allows app logs through)
    global logger  # rebind module-level variable
    logger = get_repl_logger(
        "browser_tools",
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        propagate=args.all_logs,
    )
    print("Browser Tools REPL. Menu repeats each turn. Type /exit to quit.")
    while True:
        # Always show menu at start of loop to keep tools visible
        _print_menu()
        try:
            raw = input("\nSelect tool: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting REPL.")
            break
        if not raw:
            continue
        lower = raw.lower()
        if lower in _EXIT_COMMANDS:
            print("Exiting REPL.")
            break
        if lower in _HELP_COMMANDS:
            # Help simply reprints (already printed) so continue
            continue
        spec = _find_tool(raw)
        if spec is None:
            print("Unknown selection. Type /help for list of tools.")
            continue
        await _run_tool(spec)

    # Always attempt to close browser
    try:
        await close_browser()
    except Exception:  # pragma: no cover - defensive
        logger.debug("Suppressed error closing browser", exc_info=True)


if __name__ == "__main__":  # pragma: no cover - manual execution path
    asyncio.run(main())
