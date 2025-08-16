"""Agent responsible for producing the system architecture/design for a coding task."""

import logging

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


SYSTEM_DESIGN_PROMPT = """
Role: Expert Software Architect

Goal: Produce a concise, basic architecture brief for a software assignment that downstream agents
(planner, implementer, tester) can consume.

Output: Markdown only, short and actionable. Use the following sections:

1. Summary
    - One-paragraph problem statement and success criteria.

2. Assumptions
    - Bullet list of key assumptions made to proceed.

3. Tech Stack
    - Language/runtime (one) with a brief rationale.
    - Frameworks/libraries (3-6) with one-line reasons.

4. Project Structure
    - Directory tree (code block) with key files/folders relevant to the stack.

5. Components
    - List components; for each: responsibilities, main interfaces (inputs/outputs), dependencies.

6. Data Model
    - Entities, key fields, relationships; storage choice and why.

7. Key Interactions
    - One or two primary flows described in 3-5 bullets each.

8. Testing Strategy
    - Levels (unit/integration/e2e), tools, what to test, minimal coverage target.

9. Constraints & Open Questions
    - Constraints to respect.
    - Questions needing clarification.

Guidance:
- Be brief and opinionated; avoid diagrams, deployment details, CI/CD, and long alternatives.
- No code or pseudocode; no shell commands.
- Use relative paths in the project structure.
- If details are missing, make reasonable assumptions and list them above.
- Target 300-600 words total.
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
