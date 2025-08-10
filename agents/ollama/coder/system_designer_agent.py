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
You are an expert software architect. You will receive a software assignment. You will create an
architectural design for the assignment. The design should include:
- the selected language to use
- the libraries and frameworks to be used
- the directory structure for the project
- the main components and their interactions
- the testing strategy
This design will be used to create an implementation plan.
"""


system_designer_agent = Agent(
    name="SYSTEM_DESIGNER_AGENT",
    description="Creates an architectural/system design for a software assignment.",
    instruction=SYSTEM_DESIGN_PROMPT,
    model=model.model,
    options=model.options,
    tools=[],  # No VC tools needed for pure design
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
