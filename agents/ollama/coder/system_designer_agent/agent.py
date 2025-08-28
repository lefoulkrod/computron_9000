"""System designer agent implementation."""

import logging

from agents.ollama.coder.system_designer_agent.models import SystemDesign, generate_schema_summary
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name

logger = logging.getLogger(__name__)


# Use the architect model for system design tasks
model = get_model_by_name("coder_architect")


_SCHEMA_SUMMARY = generate_schema_summary()

SYSTEM_DESIGN_PROMPT = f"""
Role: Expert Software Architect

Goal: Produce a clear, complete, and strictly structured system design that downstream agents
(planner, implementer, tester) can consume programmatically.

STRICT OUTPUT
- Return ONLY valid JSON that conforms to the SystemDesign schema below.
- No markdown, no comments, no code fences, and no prose outside the JSON.

Schema (types) summary:
{_SCHEMA_SUMMARY}

Requirements and guidance
- Choose exactly one primary programming language (set SystemDesign.language).
- Choose exactly one dependency manager appropriate for that language
	(set SystemDesign.dependency_manager).
- Choose exactly one primary test framework/tool (set SystemDesign.test_framework).
- Derive reasonable assumptions where details are missing; list them in SystemDesign.assumptions.
- Do NOT include code samples, pseudocode, shell commands, deployment details, CI/CD steps, or ADRs.

Artifacts
- Provide an exhaustive and cohesive SystemDesign.artifacts array.
- Each artifact MUST include: name, path, user_stories, detailed_requirements, acceptance_criteria.
- depends_on is optional; include when the artifact relies on other artifacts by name.
- Use relative paths only; ensure paths are unique across artifacts.
- Avoid duplicating user stories across artifacts; place each story with the owning artifact.
- User stories MUST use: "As a <role> I want <goal> so that <reason>".

Packages
- In SystemDesign.packages, list notable frameworks, libraries, or tools (runtime and dev),
	excluding the primary language, dependency manager, and test framework.
- Use simple lowercase package names without versions
	(e.g., fastapi, sqlalchemy, redis, pytest-cov).
"""


system_designer_agent = Agent(
    name="SYSTEM_DESIGNER_AGENT",
    description="Creates an architectural/system design for a software assignment.",
    instruction=SYSTEM_DESIGN_PROMPT,
    model=model.model,
    options=model.options,
    tools=[],  # No execution tools needed for pure design
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(system_designer_agent)
after_model_call_callback = make_log_after_model_call(system_designer_agent)
system_designer_agent_tool = make_run_agent_as_tool_function(
    agent=system_designer_agent,
    tool_description="""
	Produce a clear, actionable software architecture for the given assignment.
	""",
    result_type=SystemDesign,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

__all__ = [
    "system_designer_agent",
    "system_designer_agent_tool",
]
