"""Architect agent implementation."""

from agents.ollama.coder.architect_agent.models import (
    LowLevelDesign,
    generate_schema_summary,
)
from agents.ollama.sdk import make_run_agent_as_tool_function
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad

_SCHEMA_SUMMARY = generate_schema_summary()

NAME = "ARCHITECT_AGENT"
DESCRIPTION = "Creates a detailed low-level design for a software assignment."
SYSTEM_PROMPT = f"""
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
TOOLS = [save_to_scratchpad, recall_from_scratchpad]

architect_agent_tool = make_run_agent_as_tool_function(
    name=NAME,
    description=DESCRIPTION,
    instruction=SYSTEM_PROMPT,
    tools=TOOLS,
    result_type=LowLevelDesign,
)

__all__ = [
    "DESCRIPTION",
    "NAME",
    "SYSTEM_PROMPT",
    "TOOLS",
    "architect_agent_tool",
]
