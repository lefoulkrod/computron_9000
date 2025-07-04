# Standard library imports
"""Definition of the COMPUTRON_9000 LLM agent.

This file configures the core AI agent with its model, tools, and logging capabilities.
"""

# Third-party imports
from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.models.lite_llm import LiteLlm

# Local imports
from agents.adk.callbacks.callbacks import log_llm_request_callback, log_llm_response_callback
from tools.code.execute_code import execute_python_program, execute_nodejs_program
from .web import web_agent
from .file_system import file_system_agent, run_filesystem_agent
from agents.prompt import ROOT_AGENT_PROMPT
from .model_utils import get_adk_model
from tools.misc.datetime import datetime_tool

"""
Agent configuration for COMPUTRON_9000

This LlmAgent instance defines the core AI system with:
- Multi-modal capabilities
- File system access
- Web search/processing
- Date/time functions
- Code execution environments
- Logging middleware
"""

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
        AgentTool(agent=web_agent,),
        datetime_tool,
        execute_python_program,
        execute_nodejs_program,
        #run_filesystem_agent
    ],
    sub_agents=[
        #file_system_agent,
        #web_agent
    ],
    after_model_callback=log_llm_response_callback,
    before_model_callback=[log_llm_request_callback],
)

