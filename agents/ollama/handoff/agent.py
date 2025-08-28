"""The agent for handing off execution to other agents."""

import logging

from agents.ollama.sdk import Agent
from agents.ollama.sdk.higher_order import make_run_agent_as_tool_function
from config import load_config
from models import get_model_by_name

from .prompt import PROMPT

config = load_config()
logger = logging.getLogger(__name__)

model = get_model_by_name("handoff_agent")

handoff_agent: Agent = Agent(
    name="HANDOFF_AGENT",
    description="HANDOFF_AGENT is a simple agent designed to handoff execution to other agents.",
    instruction=PROMPT,
    model=model.model,
    options=model.options,
    tools=[],
    think=model.think,
)

handoff_agent_tool = make_run_agent_as_tool_function(
    agent=handoff_agent,
    tool_description="""
    HANDOFF_AGENT is a simple agent designed to handoff execution to other agents.
    """,
)
