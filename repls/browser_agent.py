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
from typing import TYPE_CHECKING, Final

from agents.ollama.browser import browser_agent
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    run_tool_call_loop,
)

if TYPE_CHECKING:  # Avoid runtime import, only for type hints
    from agents.types import Agent
from logging_config import setup_logging
from tools.browser import close_browser

logger = logging.getLogger(__name__)


PROMPT: Final = "Enter instruction or URL (commands: /help, /exit): "


# Module-level message history for this REPL session
_message_history: list[dict[str, str]] = []


def _insert_system_message(agent: Agent) -> None:
    """Ensure the first message is the agent's system prompt.

    Args:
        agent: The agent whose instruction seed should be applied.
    """
    if _message_history and _message_history[0].get("role") == "system":
        _message_history.pop(0)
    _message_history.insert(0, {"role": "system", "content": agent.instruction})


def _build_arg_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="BROWSER_AGENT REPL")


async def _run_once(user_text: str) -> None:
    """Append user input and run a single agent tool-call loop turn.

    The loop yields assistant message content incrementally. We log content
    as it arrives. Tool results are stored in the internal message history
    but not printed directly.
    """
    try:
        _message_history.append({"role": "user", "content": user_text})
        before_cb = make_log_before_model_call(browser_agent)
        after_cb = make_log_after_model_call(browser_agent)
        async for content, thinking in run_tool_call_loop(
            messages=_message_history,
            tools=browser_agent.tools,
            model=browser_agent.model,
            think=browser_agent.think,
            model_options=browser_agent.options,
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
    _build_arg_parser().parse_args()
    # Seed the conversation with the agent system message
    _insert_system_message(browser_agent)
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
