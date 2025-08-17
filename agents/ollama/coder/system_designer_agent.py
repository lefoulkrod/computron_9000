"""Agent responsible for producing the system architecture/design for a coding task."""

import logging

from agents.ollama.coder.system_design_models import generate_schema_summary
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

Goal: Produce a comprehensive structured system design for a software assignment that downstream
agents (planner, implementer, tester) can consume programmatically.

STRICT OUTPUT: Return ONLY valid JSON matching the SystemDesign schema below. No markdown, no
explanatory prose outside JSON. Do not add comments. Do not wrap in code fences.

Schema (types) summary:
{_SCHEMA_SUMMARY}

Requirements & Guidance:
- You MUST pick and justify exactly one primary programming language.
- You MUST pick exactly one dependency manager appropriate
    for the language (Python: uv or poetry; Node.js: pnpm or npm; Rust: cargo; Go: go-mod).
- You SHOULD (when applicable) pick exactly one environment/version manager:
    Python: pyenv (preferred) or asdf; Node.js: nvm (preferred) or asdf; Ruby: rbenv or asdf;
    Multi-language: asdf. Justify the choice.
- If the ecosystem rarely needs a separate env manager (e.g. Go) you do not need to include one.
- Derive reasonable assumptions where details are missing.
- Avoid code samples, pseudocode, shell commands, deployment details, CI/CD, or extraneous ADRs.
 - Provide a comprehensive project_structure: include all directories and files
     needed for implementation, testing, configuration, packaging, and operations (e.g. src/,
     tests/, docs/, infra/ or deployment/, scripts/, configs/, tooling, linters). Omit only trivial
     build artifacts.
 - Provide an exhaustive components list that decomposes the system into cohesive, loosely
     coupled units.
 - For EACH component you MUST include a "paths" array listing one or more relative paths
     drawn from project_structure.path values that the component primarily owns / implements.
     Every component must map to at least one path and only to paths that appear in
     project_structure. This mapping enables the planner to group implementation steps.
- In the packages list include notable frameworks, libraries or tools (runtime & dev) beyond the
    primary language, dependency manager, environment manager and test framework. Use simple
    lowercase package names (e.g. fastapi, sqlalchemy, redis, pytest-cov) without versions.
- For each component supply a comprehensive list covering core and
    edge interactions. Use the format: "As a <role> I want <goal> so that <reason>". Do not invent
    obviously duplicate stories across components—place each story with the component that owns
    fulfilling it.
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
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
