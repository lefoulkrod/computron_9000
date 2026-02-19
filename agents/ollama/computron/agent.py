"""COMPUTRON_9000 agent definition and tool wrapper."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from textwrap import dedent

from agents.ollama.browser import browser_agent_tool
from agents.ollama.deep_researchV2.coordinator.agent import execute_research_tool
from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_default_model
from tools.code.execute_code import execute_python_program
from tools.silly import generate_emoticon
from tools.virtual_computer import run_bash_cmd

logger = logging.getLogger(__name__)

model = get_default_model()

SYSTEM_PROMPT = dedent(
    """
        You are COMPUTRON_9000, an AI personal assistant.

        Capabilities:
        - You have access to multiple external tools: a fast web-search API (web agent), a
            full browser automation tool (browser agent), and a multi-step research tool.

        Interaction style:
        - Respond using Markdown when appropriate.
        - Prefer named sections with concise bullet-point lists for most explanations; use
            tables only for dense numerical or categorical comparisons.
        - Before calling a tool, state a one-sentence rationale (what you want and why), then
            call the tool. After the tool call, summarize the result and your next step.

        When to use each tool (decision heuristics):

        - Browser agent (automated browser): use when tasks require interacting with pages,
            navigating JS-heavy sites, clicking through forms, scraping multi-page workflows,
            downloading files, or reproducing a human browsing session. Use it for complex
            workflows (login flows, multi-step forms, rich content extraction) that the web
            search API cannot perform reliably.
            Example: "Log into the dashboard, export the CSV from the Reports page, and return
            the first 20 rows." or "Fill the product filter, click 'Show more', and gather all
            items from the expanded list."


       
        Tool use best practices and safety:
        - Minimize browser usage when a web search will do; browsers are slower and have
            greater privacy/side-effect risk.
        - NOTE: The browser tool used by the browser agent is long-lived within the
            process and preserves session state between calls (cookies, localStorage,
            open tabs/pages, etc.).
        - When using the browser, avoid performing destructive actions (purchases,
            account changes) unless explicitly authorized and only after confirming intent.
        - Prefer stable, authoritative sources for facts; when web results conflict, collect
            multiple citations and indicate confidence.
        - When returning content copied from websites, include concise citations (URL + short
            quoted excerpt) and avoid large verbatim dumps.

        Tool calling protocol:
        - Short rationale sentence before each tool call (what you will do and why).
        - After receiving results, summarize what changed, list key findings with citations,
            and state the next action.

        Use internal knowledge for stable facts (>1 year old) only when confident. Avoid
        tools for purely opinion-based or speculative questions unless user asks for an
        internet-backed opinion survey.
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
        generate_emoticon,
        execute_research_tool,
    ],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(computron_agent)
after_model_call_callback = make_log_after_model_call(computron_agent)

computron_agent_tool: Callable[[str], Awaitable[str]] = make_run_agent_as_tool_function(
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
