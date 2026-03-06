"""Interactive REPL for the BROWSER_AGENT.

Type a URL or instruction; the agent will decide when to call open_url.
This REPL maintains a conversation by preserving the tool-loop message history
across turns. On shutdown, the shared Playwright browser is closed cleanly.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
from typing import Final

from agents.ollama.browser import DESCRIPTION, NAME, SYSTEM_PROMPT, TOOLS
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    run_tool_call_loop,
)
from agents.types import Agent
from config import load_config
from logging_config import setup_logging
from tools.browser import close_browser

logger = logging.getLogger(__name__)


PROMPT: Final = "Enter instruction or URL (commands: /help, /exit): "


# Module-level message history for this REPL session
_message_history: list[dict[str, str]] = []


def _insert_system_message() -> None:
    """Ensure the first message is the agent's system prompt."""
    if _message_history and _message_history[0].get("role") == "system":
        _message_history.pop(0)
    _message_history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BROWSER_AGENT REPL")
    parser.add_argument(
        "--command",
        "-c",
        type=str,
        help="Run a single command and exit (non-interactive mode)",
    )
    return parser


async def _run_once(user_text: str) -> None:
    """Append user input and run a single agent tool-call loop turn.

    The loop yields assistant message content incrementally. We log content
    as it arrives. Tool results are stored in the internal message history
    but not printed directly.
    """
    try:
        _message_history.append({"role": "user", "content": user_text})
        # Construct a fresh agent using the default model from config
        cfg = load_config()
        default_model = cfg.get_default_model()
        agent = Agent(
            name=NAME,
            description=DESCRIPTION,
            instruction=SYSTEM_PROMPT,
            tools=TOOLS,
            model=default_model.model,
            think=default_model.think,
            options=default_model.options,
        )
        before_cb = make_log_before_model_call(agent)
        after_cb = make_log_after_model_call(agent)
        async for content, thinking in run_tool_call_loop(
            messages=_message_history,
            agent=agent,
            before_model_callbacks=[before_cb],
            after_model_callbacks=[after_cb],
        ):
            if content:
                logger.info("%s", content)
            # Optionally surface thinking at debug level
            if thinking:
                logger.debug("[thinking] %s", thinking)
    except Exception:  # pragma: no cover - REPL safety
        logger.exception("Agent error")


async def main() -> None:
    """Run an interactive loop that forwards input to BROWSER_AGENT.

    The loop accepts simple commands (/help, /exit). On exit, the shared
    Playwright browser is closed via tools.browser.close_browser.
    """
    # Ensure global logging is configured once for the process. REPL logs
    # are governed by the global config ('repls' logger level set in setup).
    setup_logging()
    args = _build_arg_parser().parse_args()
    # Seed the conversation with the agent system message
    _insert_system_message()

    # Non-interactive mode: run single command and exit
    if args.command:
        logger.info("Running command: %s", args.command)
        await _run_once(args.command)
        with contextlib.suppress(Exception):
            await close_browser()
        return

    # Interactive mode
    logger.info("Starting BROWSER_AGENT REPL. Type /help for commands.")
    while True:
        try:
            user_text = input(f"\n{PROMPT}").strip()
        except (EOFError, KeyboardInterrupt):
            logger.info("Exiting REPL.")
            break
        if not user_text:
            continue
        if user_text.startswith("/"):
            cmd = user_text[1:].strip().lower()
            if cmd == "help":
                logger.info("Commands: /help, /exit")
                continue
            if cmd == "exit":
                logger.info("Exiting REPL.")
                break
            logger.info("Unknown command. Type /help for help.")
            continue

        await _run_once(user_text)

    # Always close the shared browser before exiting
    with contextlib.suppress(Exception):
        await close_browser()


if __name__ == "__main__":  # pragma: no cover - manual execution path
    asyncio.run(main())
