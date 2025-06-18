# Standard library imports
"""Definition of the COMPUTRON_9000 LLM agent."""

# Third-party imports
from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.models.lite_llm import LiteLlm

from tools.web.get_webpage import get_webpage
from .file_system import file_system_agent
from agents.prompt import ROOT_AGENT_PROMPT
from . import get_adk_model
from tools.misc.datetime import datetime_tool
from tools.web.search_google import search_google

MODEL = get_adk_model()

computron_agent = LlmAgent(
    name="COMPUTRON_9000",
    model=LiteLlm(
        model=MODEL, 
    ),
    description=(
        "COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed to assist with a wide range of tasks."
    ),
    instruction=ROOT_AGENT_PROMPT,
    tools=[
        AgentTool(agent=file_system_agent,),
        datetime_tool,
        get_webpage,
    ],
)

