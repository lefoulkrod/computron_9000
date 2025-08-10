"""The agent for the coder development workflow functionality."""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name
from tools.virtual_computer import (
    get_current_working_directory,
    read_file_directory,
    run_bash_cmd,
    write_file,
)

logger = logging.getLogger(__name__)

model = get_model_by_name("coder_developer")

coder_dev_agent = Agent(
    name="CODER_DEV_AGENT",
    description="An agent designed to create, analyze, execute, and test code.",
    instruction="""
You are a coding agent. You will be provided with a coding assignment.
You have access to a virtual computer through your tools.
All of your work in the virtual computer will be done in a workspace folder that is created for your assignment.
Always run all bash commands relative to the current working directory.
For example, use `cd game_folder` NOT `cd /game_folder` or `cd ~/game_folder`..
You may also use `${PWD}/game_folder` to refer to the current working directory.
Don't forget linux is case-sensitive. 
Always install required packages in the current working directory. NEVER install packages globally.
Always use the `read_file_directory` tool to ensure files exist before running commands on them.
When completing a coding assignment always check that all files that interact with the current assignment exist and are correct.
Update them if necessary to complete the assignment. Update their related tests as well.
For every coding instruction you receive, you MUST:
- Use the available tools to complete the assignment.
- Check the current project layout and stay consistent with it (e.g., file names, structure, test locations).
- Always verify the code is correct before completing.
- Write unit tests for the code you write.
- Run the unit tests to ensure the code works as expected.
After completing the assignment, return brief summary of your work.
""",
    model=model.model,
    options=model.options,
    tools=[
        run_bash_cmd,
        write_file,
        read_file_directory,
        get_current_working_directory,
    ],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(coder_dev_agent)
after_model_call_callback = make_log_after_model_call(coder_dev_agent)
coder_dev_agent_tool = make_run_agent_as_tool_function(
    agent=coder_dev_agent,
    tool_description="""
    The coding agent can perform code generation, analysis, execution, and testing 
    based on the instructions provided.
    """,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
