"""COMPUTRON_9000 agent definition and tool wrapper."""

from __future__ import annotations

import logging
from textwrap import dedent

from agents.ollama.browser import browser_agent_tool
from agents.ollama.deep_researchV2.coordinator.agent import execute_research_tool
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.ollama.web import web_agent_tool
from agents.types import Agent
from models import get_default_model
from tools.code.execute_code import execute_python_program
from tools.silly import generate_emoticon
from tools.virtual_computer import run_bash_cmd

logger = logging.getLogger(__name__)

model = get_default_model()

SYSTEM_PROMPT = dedent(
    """
    You are COMPUTRON_9000, a friendly, knowledgeable, and reliable AI personal assistant.
    Your primary goal is to help the user accomplish a wide range of tasks.

    Capabilities:
    - You have access to a variety of tools to assist you.

    Interaction style:
    - Be clear and concise, using markdown (lists, tables, code blocks) when they help.
    - Before calling a tool, give a one-sentence rationale, then call it.
    - After a tool call, summarize the result plainly.
    - Keep emoticons out of code blocks and never let them replace substance.

    Tool guidelines:
    - Use `run_web_agent_as_tool` for up-to-date information from the web.
    - Use `run_browser_agent_tool` to control a browser to achieve actions on web pages.
    - Use `execute_research_tool` to perform a deep research on a topic.
    Tool usage policy:
    - Use internal knowledge for stable facts (>1 year old) when confident.
    - Avoid tools for purely opinion-based questions.
    """
)

computron_agent: Agent = Agent(
    name="COMPUTRON_9000",
    description=(
        "COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed "
        "to assist with a wide range of tasks."
    ),
    instruction=SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[
        execute_python_program,
        run_bash_cmd,
        browser_agent_tool,
        web_agent_tool,
        generate_emoticon,
        execute_research_tool,
    ],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(computron_agent)
after_model_call_callback = make_log_after_model_call(computron_agent)

computron_agent_tool = make_run_agent_as_tool_function(
    agent=computron_agent,
    tool_description=computron_agent.description,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)

# Backwards compatibility exports
computron = computron_agent
agent_before_callback = before_model_call_callback
agent_after_callback = after_model_call_callback
run_computron_agent_as_tool = computron_agent_tool

__all__ = [
    "agent_after_callback",
    "agent_before_callback",
    "computron",
    "computron_agent",
    "computron_agent_tool",
    "run_computron_agent_as_tool",
]
