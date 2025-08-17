"""Coder agents REPL with simple /agent switching.

Supported agent keys (initial selection via -a or in REPL with /agent <key>):
    workflow, designer, planner, coder, test_planner, test_executor, verifier

Commands inside the REPL:
    /agent <key>   Switch current agent/workflow
    /help          Show command help
    /exit          Exit the REPL

Any other input line runs the current agent (or full workflow) using that line as the
prompt. Prompts are adapted per agent for convenience (designer/planner/coder). The
verifier (gating) consumes execution and plan JSON directly for workflow; test_planner
and test_executor provide isolated planning and execution.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from agents.ollama.coder.coder_agent import coder_agent_tool
from agents.ollama.coder.planner_agent import planner_agent_tool
from agents.ollama.coder.system_design_models import SystemDesign
from agents.ollama.coder.system_designer_agent import system_designer_agent_tool
from agents.ollama.coder.test_executor_agent import test_executor_agent_tool
from agents.ollama.coder.test_planner_agent import test_planner_agent_tool
from agents.ollama.coder.verifier_agent import verifier_agent_tool
from agents.ollama.coder.workflow import workflow
from repls.repl_logging import get_repl_logger

if TYPE_CHECKING:  # type-only imports
    from collections.abc import Awaitable, Callable
from logging_config import setup_logging

logger = get_repl_logger("workflow")
logger.setLevel(logging.INFO)

setup_logging()


AGENT_KEYS = [
    "workflow",
    "designer",
    "planner",
    "coder",
    "test_planner",
    "test_executor",
    "verifier",
]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run coder workflow or a single agent, then drop into a REPL for more. "
            "Switch with /agent <name>, exit with /exit."
        )
    )
    parser.add_argument(
        "-a",
        "--agent",
        choices=AGENT_KEYS,
        default="workflow",
        help="Agent key to run first (default: workflow).",
    )
    parser.add_argument(
        "-p",
        "--prompt",
        help="Initial prompt (if omitted and not workflow you will be prompted).",
    )
    return parser


def _ensure_prompt(prompt: str | None) -> str:
    if prompt and prompt.strip():  # fast path
        return prompt
    return input("Enter a prompt: ")


def _maybe_parse_json(text: str) -> object | None:
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return None


async def _run_workflow(user_prompt: str) -> None:
    logger.info("--- Running workflow ---")
    async for result in workflow(user_prompt):
        logger.info("Step result: %s", result)


def _pretty_print(obj: object) -> str:
    """Return a JSON pretty-printed string for either a pydantic model or raw object."""
    try:
        data = obj.model_dump() if isinstance(obj, BaseModel) else obj
        return json.dumps(data, indent=2, sort_keys=True)
    except Exception:  # defensive pretty printing
        logger.exception("Pretty print failure")
        try:
            return json.dumps(str(obj), indent=2)
        except (TypeError, ValueError):
            return repr(obj)


def _process_agent_response[ModelT: BaseModel](
    raw: object, model_cls: type[ModelT] | None, agent_name: str
) -> None:
    """Handle agent response: parse JSON, validate optional model, pretty print.

    Strategy:
        1. Coerce raw to string (LLM responses assumed stringifiable).
        2. Attempt json.loads -> if fail, log raw text.
        3. If model_cls provided, validate; on success pretty print model; on failure
           log validation error and pretty print parsed JSON.
        4. If no model_cls, pretty print parsed JSON structure.
    """
    text = str(raw)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Do not raise or log stack trace; emit concise message and raw text
        logger.warning("%s output JSON parse failed; returning raw text", agent_name)
        logger.info("%s", text)
        return

    if model_cls is not None:
        try:
            model_obj = model_cls.model_validate(parsed)
        except ValidationError as exc:
            # Concise validation error without stack trace (retain structured errors)
            logger.warning(
                "%s model validation failed; returning parsed JSON. Errors: %s",
                agent_name,
                exc.errors(),
            )
        except (TypeError, ValueError) as exc:  # pragma: no cover - unexpected path
            logger.warning(
                "%s unexpected validation issue (%s); returning parsed JSON",
                agent_name,
                exc,
            )
        else:
            logger.info("%s model validated successfully", agent_name)
            logger.info("%s", _pretty_print(model_obj))
            return
    logger.info("%s", _pretty_print(parsed))


async def _invoke_agent(
    user_prompt: str,
    tool_fn: Callable[[str], Awaitable[object]],
    agent_name: str,
    model_cls: type[BaseModel] | None = None,
) -> None:
    """Invoke an agent tool and process response generically.

    Args:
        user_prompt: Prompt string provided by user / constructed wrapper.
        tool_fn: Awaitable function accepting the prompt returning raw response.
        agent_name: Name for logging context.
        model_cls: Optional Pydantic model class to validate JSON output.
    """
    resp = await tool_fn(user_prompt)
    _process_agent_response(resp, model_cls, agent_name)


async def _run_designer(user_prompt: str) -> None:
    await _invoke_agent(user_prompt, system_designer_agent_tool, "SystemDesign", SystemDesign)


async def _run_planner(user_prompt: str) -> None:
    plan_prompt = (
        "Create an implementation plan for the software assignment "
        f'"{user_prompt}". Return only the strict JSON array of steps as specified.'
    )
    await _invoke_agent(plan_prompt, planner_agent_tool, "Planner")


async def _run_coder(user_prompt: str) -> None:
    step_input = (
        "Follow these instructions in the headless execution environment. Create tests "
        "listed and run them. Then implement code to pass tests. Keep changes minimal.\n\n"
        f"Step 1 - Standalone task: {user_prompt}"
    )
    await _invoke_agent(step_input, coder_agent_tool, "Coder")


async def _run_verifier(user_prompt: str) -> None:
    parsed = _maybe_parse_json(user_prompt)
    if parsed is None:
        payload = {
            "commands": [
                {"run": user_prompt, "timeout_sec": 120},
            ],
            "instruction": (
                "Execute the single short-lived verification command and return the strict "
                "JSON summary specified by your system prompt."
            ),
        }
        user_prompt = json.dumps(payload)
        logger.info("Verifier constructed single-command payload")
    await _invoke_agent(user_prompt, verifier_agent_tool, "Verifier")


async def _run_test_planner(user_prompt: str) -> None:
    parsed = _maybe_parse_json(user_prompt)
    if parsed is None:
        payload = {"assignment": user_prompt, "coder_output": ""}
        user_prompt = json.dumps(payload)
        logger.info("Test planner constructed minimal payload from text prompt")
    await _invoke_agent(user_prompt, test_planner_agent_tool, "TestPlanner")


async def _run_test_executor(user_prompt: str) -> None:
    parsed = _maybe_parse_json(user_prompt)
    if parsed is None:
        payload = {"commands": [{"run": user_prompt, "timeout_sec": 120}]}
        user_prompt = json.dumps(payload)
        logger.info("Test executor constructed single-command payload")
    await _invoke_agent(user_prompt, test_executor_agent_tool, "TestExecutor")


async def _run_agent(agent: str, prompt: str) -> None:
    if agent == "workflow":
        await _run_workflow(prompt)
    elif agent == "designer":
        await _run_designer(prompt)
    elif agent == "planner":
        await _run_planner(prompt)
    elif agent == "coder":
        await _run_coder(prompt)
    elif agent == "verifier":
        await _run_verifier(prompt)
    elif agent == "test_planner":
        await _run_test_planner(prompt)
    elif agent == "test_executor":
        await _run_test_executor(prompt)
    else:
        logger.error("Unknown agent: %s", agent)


async def _repl(current_agent: str) -> None:
    logger.info(
        "Entering REPL. Current agent: %s (use /agent <name>, /help, /exit)",
        current_agent,
    )
    while True:
        try:
            line = input(f"[{current_agent}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            logger.info("Exiting REPL (interrupt)")
            break
        if not line:
            continue
        if line.startswith("/agent "):
            _, _, name = line.partition(" ")
            name = name.strip()
            if name in AGENT_KEYS:
                current_agent = name
                logger.info("Switched agent to %s", current_agent)
            else:
                logger.warning("Unknown agent '%s' (choices: %s)", name, ", ".join(AGENT_KEYS))
            continue
        if line == "/exit":
            logger.info("Exiting REPL")
            break
        if line == "/help":
            logger.info("Commands: /agent <name>, /exit, /help")
            continue
        await _run_agent(current_agent, line)


async def main() -> None:
    """Parse arguments, optionally run initial agent, then enter REPL."""
    parser = _build_arg_parser()
    args = parser.parse_args()
    agent = args.agent
    # Optional initial run if prompt provided; otherwise skip to REPL
    if args.prompt:
        await _run_agent(agent, args.prompt)
    # Enter REPL regardless
    await _repl(agent)


if __name__ == "__main__":  # pragma: no cover - manual execution path
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
