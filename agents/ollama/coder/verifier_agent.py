"""Agent that verifies code by running tests and static checks in a headless execution environment.

Returns a structured JSON summary suitable for gating step acceptance.
"""

from __future__ import annotations

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name

# Import the callable directly to avoid mypy resolving the symbol as the submodule
from tools.virtual_computer.run_bash_cmd import run_bash_cmd

logger = logging.getLogger(__name__)


model = get_model_by_name("coder_architect")


VERIFIER_SYSTEM_PROMPT = (
    "You are VerifierAgent. Your only job is to run the specific verification commands "
    "provided in the step context via tools and return STRICT JSON. Do not assume any "
    "particular language or framework. Never start servers or long-running processes.\n\n"
    "Return JSON with this shape (no prose):\n"
    "{\n"
    '  "success": bool,\n'
    '  "passed": int,\n'
    '  "failed": int,\n'
    '  "outcomes": [ { "command": str, "exit_code": int, "ok": bool, '
    '"stdout_preview": str | null, "stderr_preview": str | null } ]\n'
    "}\n"
)


verifier_agent = Agent(
    name="VERIFIER_AGENT",
    description="Runs plan-provided verification commands; returns strict JSON summary.",
    instruction=VERIFIER_SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[run_bash_cmd],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(verifier_agent)
after_model_call_callback = make_log_after_model_call(verifier_agent)
verifier_agent_tool = make_run_agent_as_tool_function(
    agent=verifier_agent,
    tool_description=(
        "Verify the workspace by running tests and static checks; return strict JSON"
    ),
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
