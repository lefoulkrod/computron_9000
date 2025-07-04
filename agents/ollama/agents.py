import logging
from typing import Any, Callable, Dict, List

from agents.ollama.sdk import Agent

from agents.ollama.sdk import make_run_agent_as_tool_function
from agents.prompt import ROOT_AGENT_PROMPT, WEB_AGENT_PROMPT
from config import load_config
from tools.code.execute_code import execute_python_program
from tools.fs import list_directory_contents, read_file_contents, write_text_file
from tools.misc import datetime_tool
from tools.web import search_google
from tools.web import get_webpage_substring, get_webpage_summary_sections

config = load_config()
logger = logging.getLogger(__name__)

web_agent: Agent = Agent(
    name="WEB_AGENT",
    description="WEB_AGENT is a simple agent designed to handle web-related tasks such as searching, browsing, and retrieving information from the web.",
    instruction=WEB_AGENT_PROMPT,
    model=config.llm.model,
    options={
        "num_ctx": config.llm.num_ctx,
    },
    tools=[ 
        get_webpage_summary_sections,
        get_webpage_substring,
        search_google,
    ],
)

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
            """
        ),
        execute_python_program,
        datetime_tool,
    ],
)

root_agent: Agent = Agent(
    name="ROOT_AGENT",
    description="ROOT_AGENT is a simple agent designed to handoff tasks to other agents.",
    instruction="""
    Always handoff tasks to the appropriate agent based on the task type. If the task is not recognized, respond with 'I don't know how to handle that.'
    Do not attempt to execute tools that you don't have access to. If you learn about another agents tool in it's response, do not attempt to use it.
    Always ask the sub-agents to exeucte their own tools.
    """,
    model=config.llm.model,
    options={
        "num_ctx": config.llm.num_ctx,
    },
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
