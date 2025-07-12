import logging

from agents.ollama.sdk import Agent

from config import load_config
from models import get_default_model
from .deep_research import deep_research_agent_tool
from .computron_agent import run_computron_agent_as_tool
from .web_agent import web_agent_tool
config = load_config()
logger = logging.getLogger(__name__)

model = get_default_model()

root_agent: Agent = Agent(
    name="ROOT_AGENT",
    description="ROOT_AGENT is a simple agent designed to handoff tasks to other agents.",
    instruction="""
    Always handoff tasks to the appropriate agent based on the task type. If the task is not recognized, respond with 'I don't know how to handle that.'
    Do not attempt to execute tools that you don't have access to. If you learn about another agents tool in it's response, do not attempt to use it.
    Always ask the sub-agents to exeucte their own tools.
    """,
    model=model.model,
    options=model.options,
    tools=[
        deep_research_agent_tool,
        run_computron_agent_as_tool,
        web_agent_tool
    ],
)
