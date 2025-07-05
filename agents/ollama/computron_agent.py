import logging

from agents.ollama.sdk import Agent
from agents.prompt import ROOT_AGENT_PROMPT
from config import load_config
from tools.code.execute_code import execute_python_program
from tools.misc import datetime_tool
from .web_agent import web_agent_tool

config = load_config()
logger = logging.getLogger(__name__)

computron: Agent = Agent(
    name="COMPUTRON_9000",
    description="COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed to assist with a wide range of tasks.",
    instruction=ROOT_AGENT_PROMPT,
    model=config.llm.model,
    options={
        "num_ctx": config.llm.num_ctx,
    },
    tools=[
        web_agent_tool,
        execute_python_program,
        datetime_tool,
    ],
)
