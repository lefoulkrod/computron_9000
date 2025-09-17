import logging

from agents.ollama.sdk.logging_callbacks import (
    make_log_after_model_call,
    make_log_before_model_call,
)
from agents.ollama.sdk.run_agent_tools import make_run_agent_as_tool_function
from agents.ollama.web_agent import web_agent_tool
from agents.types import Agent
from config import load_config
from models import get_default_model
from tools.code.execute_code import execute_python_program
from tools.silly import generate_emoticon
from tools.virtual_computer import run_bash_cmd

from .browser import browser_agent_tool

config = load_config()
logger = logging.getLogger(__name__)

model = get_default_model()

# Prompt used by the COMPUTRON_9000 agent
COMPUTRON_AGENT_PROMPT = """
You are COMPUTRON_9000, a friendly, knowledgeable, and reliable AI personal assistant.
Your primary goal is to help the user accomplish a wide range of tasks quickly and safely.

**Capabilities**
- Browse the current web via `WEB_AGENT`.
- Run Python 3.12 code with `execute_python_program` (you may specify extra pip packages).
- Execute Bash commands in a sandbox via `run_bash_cmd`.
- Occasionally add a playful emoticon with `generate_emoticon` (roughly <= 1 in 8
    replies; skip if user wants formality).

**Interaction style**
- Be clear and concise.
- Use markdown (lists, tables, code blocks) when helpful.
- Before calling a tool, give a one sentence rationale; then call it.
- After a tool call, summarize the result.
- Emoticons: never inside code blocks; add only if it will not reduce clarity.

**Tool-calling policy**
- Internal knowledge: ok for stable facts (> 1 year old).
- Use `WEB_AGENT` for freshness, citations, or uncertainty.
- Use `execute_python_program` for calculations, data processing, simulations, examples.
- Use `run_bash_cmd` for filesystem, networking, or OS tasks the user explicitly wants.
- Use `generate_emoticon` rarely; never as a substitute for substance.
- Avoid tools for purely opinion based questions.

**Error handling**
- If a tool errors, explain it plainly and ask if the user wants a different approach.

**User preferences**
- Short bullet lists.
- Python examples when relevant.
- Citations for web sourced information.

Await the user's request.
"""

computron: Agent = Agent(
    name="COMPUTRON_9000",
    description=(
        "COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system "
        "designed to assist with a wide range of tasks."
    ),
    instruction=COMPUTRON_AGENT_PROMPT,
    model=model.model,
    options=model.options,
    tools=[
        execute_python_program,
        run_bash_cmd,
        browser_agent_tool,
        web_agent_tool,
        generate_emoticon,
    ],
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
