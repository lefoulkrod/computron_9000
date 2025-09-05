"""Minimal deterministic agent that exercises virtual computer tools.

The agent always performs exactly these steps in order:
  1) Write a fixed multi-line text to a file
  2) Apply a line-based text patch to that file
  3) Read the file back and return True/False indicating patch success

No LLM calls are used; the logic is deterministic and uses the tool API directly.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name
from tools.virtual_computer import apply_text_patch, read_file, write_file

logger = logging.getLogger(__name__)

# Choose an existing model to satisfy Agent schema; it is not used at runtime here.
_model = get_model_by_name("coder_developer")

# Fixed inputs
_FILE_PATH = "tool_test/demo.txt"
_INITIAL_TEXT = dedent(
    """
    alpha
    beta
    gamma
    """
).lstrip("\n")
# Replace line 2 ("beta") with "delta"
_PATCH_START = 2
_PATCH_END = 2
_PATCH_REPLACEMENT = "delta\n"


def _run_sequence() -> bool:
    """Run the fixed write -> patch -> read sequence and return success.

    Returns:
        bool: True if the patch was applied and the file content matches the
        expected result; False otherwise.
    """
    # Step 1: write the initial content
    w = write_file(_FILE_PATH, _INITIAL_TEXT)
    if not w.success:
        logger.error("write_file failed: %s", w.error)
        return False

    # Step 2: apply the patch
    p = apply_text_patch(
        path=_FILE_PATH,
        start_line=_PATCH_START,
        end_line=_PATCH_END,
        replacement=_PATCH_REPLACEMENT,
    )
    if not p.success:
        logger.error("apply_text_patch failed: %s", p.error)
        return False

    # Step 3: read and verify
    r = read_file(_FILE_PATH)
    if not r.success or r.content is None:
        logger.error("read_file failed: %s", r.error)
        return False

    expected = dedent(
        """
        alpha
        delta
        gamma
        """
    ).lstrip("\n")
    ok = r.content == expected
    if not ok:
        logger.warning("content mismatch; got=%r expected=%r", r.content, expected)
    return ok


# Expose a minimal Agent object for parity with other agents (not used by logic)
tool_test_agent = Agent(
    name="TOOL_TEST_AGENT",
    description=("Deterministic agent that writes a file, patches it, then verifies the result."),
    instruction=(
        "Follow the user's instructions exactly. Use only the provided tools. "
        "Prefer apply_text_patch for edits and return the unified diff or results requested. "
        "Keep the response concise."
    ),
    model=_model.model,
    options=_model.options,
    tools=[write_file, apply_text_patch, read_file],
    think=False,
)

before_model_call_callback = make_log_before_model_call(tool_test_agent)
after_model_call_callback = make_log_after_model_call(tool_test_agent)
tool_test_agent_tool = make_run_agent_as_tool_function(
    agent=tool_test_agent,
    tool_description=(
        "Run the deterministic tool-test sequence: write a file, patch it, verify result. "
        "Returns True if patch succeeded, else False."
    ),
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
