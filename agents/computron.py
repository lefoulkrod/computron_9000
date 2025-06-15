# Standard library imports

# Third-party imports
from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.models.lite_llm import LiteLlm

# Local imports
from .file_system import file_system_agent
from . import prompt
from config import load_config

MODEL = load_config().llm.model

computron_agent = LlmAgent(
    name="COMPUTRON_9000",
    model=LiteLlm(
        model=MODEL, 
    ),
    description=(
        "COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed to assist with a wide range of tasks."
    ),
    instruction=prompt.ROOT_AGENT_PROMPT,
    tools=[
        AgentTool(agent=file_system_agent,)
    ],
)
