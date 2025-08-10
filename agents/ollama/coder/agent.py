"""The agent for code generation and code-related tasks."""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import model_configs
from tools.virtual_computer import (
    read_file_directory,
    run_bash_cmd,
    write_file,
)

from .prompt import PROMPT

logger = logging.getLogger(__name__)

model = model_configs.get_model_by_name("coder_architect")

coder_agent = Agent(
    name="CODER_AGENT",
    description="An agent designed to create, analyze, execute and test code.",
    instruction=PROMPT,
    model=model.model,
    options=model.options,
    tools=[
        run_bash_cmd,
        write_file,
        read_file_directory,
    ],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(coder_agent)
after_model_call_callback = make_log_after_model_call(coder_agent)
coder_agent_tool = make_run_agent_as_tool_function(
    agent=coder_agent,
    tool_description="""
    Create, analyze, execute and test code.
    """,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
