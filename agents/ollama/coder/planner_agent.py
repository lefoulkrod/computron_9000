"""Agent responsible for producing an actionable implementation plan from a system design."""

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


PLANNER_SYSTEM_PROMPT = """
You are an expert software architect. You will receive a software assignment and
an architectural design. Use the design to create a detailed plan for implementing the
software project. DO NOT write the code. The plan will be used by the coder agent to implement
the project. The coder agent will execute the plan step by step, in the order you provide.
The coder agent has access to a virtual computer with bash but no GUI.
The coder agent will run all commands within a workspace folder that is created for the assignment.
When returning file paths, always return relative paths.
*Each step* in the plan can optionally include:
- a description of any operations that should be performend in the virtual computer
- the names and locations of files to be created and a description of the file's purpose
- how the files should interact with other files in the project
- a list of unit tests to be created for the files in this step
Each step in the plan should be small and related to a single task.
Use as many steps as needed to complete the assignment.
You MUST return the plan as an array of JSON objects which can be provided to the coder agent.
You MUST return valid JSON.
"""


planner_agent = Agent(
    name="PLANNER_AGENT",
    description="Creates a detailed, step-by-step implementation plan from a design.",
    instruction=PLANNER_SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(planner_agent)
after_model_call_callback = make_log_after_model_call(planner_agent)
planner_agent_tool = make_run_agent_as_tool_function(
    agent=planner_agent,
    tool_description="""
    Turn a high-level design into a structured, JSON implementation plan.
    """,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
