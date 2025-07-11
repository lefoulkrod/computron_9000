import logging

from agents.ollama.sdk import Agent, make_run_agent_as_tool_function

from config import load_config
from .computron_agent import computron
from agents.models import get_model_by_name, get_default_model

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
        make_run_agent_as_tool_function(
            agent=computron,
            tool_description="""
            Run the COMPUTRON_9000 agent. It can handle a wide range of tasks including code execution, file operations, and datetime management.
            It can be used to run complex workflows so provide it detailed instructions for what you want to acheive.
            Include a step by step plan if you would like it to follow a specific sequence of operations.
            """
        ),
    ],
)
