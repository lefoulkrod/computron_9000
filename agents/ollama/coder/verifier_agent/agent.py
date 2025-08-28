"""Gating verifier agent implementation."""

from __future__ import annotations

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name

logger = logging.getLogger(__name__)


model = get_model_by_name("coder_architect")

VERIFIER_GATE_SYSTEM_PROMPT = (
    "You are GatingVerifierAgent. Decide if the step is accepted based on the test "
    "execution report.\n"
    "Inputs: assignment (what to implement), coder_output (summary of what coder did),\n"
    "test_plan (planned tests + commands), execution_report (results of those commands).\n"
    "Return ONLY STRICT JSON with schema:\n"
    "{\n"
    '  "accepted": bool,\n'
    '  "reasons": [str],\n'
    '  "fixes": [str]\n'
    "}\n\n"
    "Rules:\n"
    "- accepted must be false if execution_report.success is false or any failed outcomes.\n"
    "- Provide concise actionable fixes referencing failing commands or missing tests.\n"
    "- Never include prose outside JSON.\n"
)


verifier_agent = Agent(
    name="GATING_VERIFIER_AGENT",
    description="Determines step acceptance and fix guidance from execution report.",
    instruction=VERIFIER_GATE_SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(verifier_agent)
after_model_call_callback = make_log_after_model_call(verifier_agent)
verifier_agent_tool = make_run_agent_as_tool_function(
    agent=verifier_agent,
    tool_description=(
        "Decide acceptance based on test execution results; return VerifierDecision JSON."
    ),
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "verifier_agent",
    "verifier_agent_tool",
]
