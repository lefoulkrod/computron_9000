import logging

from agents.ollama.sdk import Agent, make_run_agent_as_tool_function, make_log_before_model_call, make_log_after_model_call
from agents.prompt import ROOT_AGENT_PROMPT
from config import load_config
from tools.code.execute_code import execute_python_program
from tools.misc import datetime_tool
from .web_agent import web_agent

config = load_config()
logger = logging.getLogger(__name__)

web_agent_before_callback = make_log_before_model_call(web_agent)
web_agent_after_callback = make_log_after_model_call(web_agent)

computron: Agent = Agent(
    name="COMPUTRON_9000",
    description="COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed to assist with a wide range of tasks.",
    instruction=ROOT_AGENT_PROMPT,
    model=config.llm.model,
    options={
        "num_ctx": config.llm.num_ctx,
    },
    tools=[
        make_run_agent_as_tool_function(
            agent=web_agent,
            tool_description="""
            Run the WEB_AGENT to perform web-related tasks such as searching, browsing, and retrieving information from the web.
            Provide detailed instructions for the web agent to follow, including specific goals or outcomes you want it to achieve.
            """,
            before_model_callbacks=[web_agent_before_callback],
            after_model_callbacks=[web_agent_after_callback],
        ),
        execute_python_program,
        datetime_tool,
    ],
)
