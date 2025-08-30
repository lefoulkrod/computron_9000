"""Architect agent implementation."""

import logging

from agents.ollama.coder.architect_agent.models import (
    LowLevelDesign,
    generate_schema_summary,
)
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name

logger = logging.getLogger(__name__)

model = get_model_by_name("coder_architect")

_SCHEMA_SUMMARY = generate_schema_summary()

ARCHITECT_PROMPT = f"""
Role: Expert Software Architect

Goal: Produce a clear, comprehensive low-level design for the given software assignment.

STRICT OUTPUT
- Return ONLY valid JSON that conforms to the LowLevelDesign schema below.
- No markdown, no comments, no code fences, and no additional text.

Schema (types) summary:
{_SCHEMA_SUMMARY}

Guidelines
- Decompose the solution into modules, types, exceptions, enums, and interactions.
- Describe for each type its functionality, interfaces, attributes, and dependencies.
- Use concise summaries; avoid code snippets or implementation details.
"""

architect_agent = Agent(
    name="ARCHITECT_AGENT",
    description="Creates a detailed low-level design for a software assignment.",
    instruction=ARCHITECT_PROMPT,
    model=model.model,
    options=model.options,
    tools=[],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(architect_agent)
after_model_call_callback = make_log_after_model_call(architect_agent)
architect_agent_tool = make_run_agent_as_tool_function(
    agent=architect_agent,
    tool_description="""
        Produce a detailed low-level design in structured JSON.
        """,
    result_type=LowLevelDesign,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "architect_agent",
    "architect_agent_tool",
]
