import logging

from agents.ollama.sdk import Agent
from agents.ollama.sdk.higher_order import make_run_agent_as_tool_function
from config import load_config
from models import get_model_by_name

config = load_config()
logger = logging.getLogger(__name__)

model = get_model_by_name("handoff_agent")

handoff_agent: Agent = Agent(
    name="HANDOFF_AGENT",
    description="HANDOFF_AGENT is a simple agent designed to handoff execution to other agents.",
    instruction="""
    You are an AI agent responsible for classifying user prompts and handing off processing to the
    appropriate agent based on how you classify the prompt. The way you handoff is by returning
    the name of the agent that should handle the request.
    You MUST return exactly one of the following strings:
    - "web" for any requests related to web content or browsing.
    - "research" for any requests related to doing research.
    - "computron" for all any general request or requests that do not fit into the other categories.
    """,
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
