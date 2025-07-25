import logging

from agents.ollama.sdk.higher_order import make_run_agent_as_tool_function
from agents.ollama.sdk.logging_callbacks import (
    make_log_after_model_call,
    make_log_before_model_call,
)
from agents.prompt import COMPUTRON_AGENT_PROMPT
from agents.types import Agent
from config import load_config
from models import get_default_model
from tools.virtual_computer import (
    read_file_or_dir_in_home_dir,
    run_bash_cmd,
    write_file_in_home_dir,
)

from .web_agent import web_agent_tool

config = load_config()
logger = logging.getLogger(__name__)

model = get_default_model()

computron: Agent = Agent(
    name="COMPUTRON_9000",
    description="COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed to assist with a wide range of tasks.",
    instruction=COMPUTRON_AGENT_PROMPT,
    model=model.model,
    options=model.options,
    tools=[web_agent_tool, run_bash_cmd, write_file_in_home_dir, read_file_or_dir_in_home_dir],
    think=model.think,
)

agent_before_callback = make_log_before_model_call(computron)
agent_after_callback = make_log_after_model_call(computron)

run_computron_agent_as_tool = make_run_agent_as_tool_function(
    agent=computron,
    tool_description=computron.description,
    before_model_callbacks=[agent_before_callback],
    after_model_callbacks=[agent_after_callback],
)
