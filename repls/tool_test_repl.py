"""Tool-test REPL that runs multiple text-patch scenarios end-to-end.

This REPL sets a workspace and invokes the agent tool three times with
increasingly complex instructions. The instructions live here and are passed
to the agent tool verbatim so we can vary scenarios without changing agent code.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from agents.ollama.tool_test import tool_test_agent_tool
from logging_config import setup_logging
from repls.repl_logging import get_repl_logger
from tools.virtual_computer.workspace import set_workspace_folder

logger = get_repl_logger("tool_test")
logger.setLevel(logging.INFO)

setup_logging()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the tool-test agent once in a workspace.")
    parser.add_argument(
        "-w",
        "--workspace",
        required=True,
        help="Workspace folder name to use (created if missing).",
    )
    return parser


async def main() -> None:
    """Parse args, set workspace, invoke three scenarios in order."""
    parser = _build_arg_parser()
    args = parser.parse_args()
    set_workspace_folder(args.workspace)

    logger.info("Workspace: %s", args.workspace)

    # Scenario 1: simple single-line replacement
    scenario1 = (
        "You are testing text patching. Return a short summary (not JSON).\n"
        "Steps:\n"
        "1) Create 'tool_test/demo.txt' with these lines:\n"
        "   alpha\n"
        "   beta\n"
        "   gamma\n"
        "2) Use apply_text_patch to replace line 2 with 'delta'.\n"
        "3) Analyze the returned unified diff and verify it reflects the intended change\n"
        "   (line 2 beta -> delta). State whether the diff is correct.\n"
        "4) Read the file, then compare its content to what the diff implies.\n"
        "5) Return a concise summary with: Diff OK: yes/no;\n"
        "   File matches diff: yes/no; and the final file content.\n"
        "   Keep it under ~10 lines.\n"
        "Important: Use only write_file, apply_text_patch, read_file.\n"
    )

    logger.info("Scenario 1: single-line replacement")
    result1 = await tool_test_agent_tool(scenario1)
    logger.info("Result 1: %s", result1)

    # Scenario 2: replace a middle multi-line block
    scenario2 = (
        "Perform a multi-line patch. Return a short summary (not JSON).\n"
        "Steps:\n"
        "1) Overwrite 'tool_test/demo.txt' with these four lines:\n"
        "   one\n"
        "   two\n"
        "   three\n"
        "   four\n"
        "2) Replace lines 2-3 using apply_text_patch with two lines:\n"
        "   TWO\n"
        "   THREE\n"
        "3) Analyze apply_text_patch's unified diff to confirm it shows the intended block\n"
        "   replacement (two,three -> TWO,THREE).\n"
        "4) Read the file and confirm it matches the diff's 'after' state.\n"
        "5) Return a concise summary with: Diff OK yes/no;\n"
        "   File matches diff yes/no; final content.\n"
        "Tools only: write_file, apply_text_patch, read_file.\n"
    )

    logger.info("Scenario 2: multi-line middle block replacement")
    result2 = await tool_test_agent_tool(scenario2)
    logger.info("Result 2: %s", result2)

    # Scenario 3: larger block patch and reduction
    scenario3 = (
        "Apply a larger block replacement. Return a short summary (not JSON).\n"
        "Steps:\n"
        "1) Overwrite 'tool_test/demo.txt' with these six lines:\n"
        "   a\n"
        "   b\n"
        "   c\n"
        "   d\n"
        "   e\n"
        "   f\n"
        "2) Replace lines 2-5 with a single line 'BUNDLE' using apply_text_patch.\n"
        "3) Analyze the unified diff to confirm it shows a reduction of lines 2-5 into one line.\n"
        "4) Read the file and verify the result matches the diff's 'after' state.\n"
        "5) Return a concise summary: Diff OK yes/no;\n"
        "   File matches diff yes/no; final content.\n"
        "Tools only: write_file, apply_text_patch, read_file.\n"
    )

    logger.info("Scenario 3: larger block replacement with reduction")
    result3 = await tool_test_agent_tool(scenario3)
    logger.info("Result 3: %s", result3)


if __name__ == "__main__":  # pragma: no cover - manual execution path
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
