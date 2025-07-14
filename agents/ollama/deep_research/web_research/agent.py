"""
Web Research Agent for web-based research tasks.

This module contains the Web Research Agent specialized for conducting
research using web sources.
"""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from tools.web import (
    get_webpage,
    get_webpage_substring,
    get_webpage_summary,
    get_webpage_summary_sections,
    html_find_elements,
    search_google,
)

from ..shared import get_agent_config
from .prompt import WEB_RESEARCH_PROMPT

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration
config = get_agent_config("web_research")
model, options = config.get_model_settings()

# Define the Web Research Agent
web_research_agent: Agent = Agent(
    name="WEB_RESEARCH_AGENT",
    description="Specialized agent for conducting research using web sources",
    instruction=WEB_RESEARCH_PROMPT,
    model=model,
    options=options,
    tools=[
        search_google,
        get_webpage,
        get_webpage_summary,
        get_webpage_summary_sections,
        get_webpage_substring,
        html_find_elements,
    ],
)

# Create standard callbacks for logging
web_research_before_callback = make_log_before_model_call(web_research_agent)
web_research_after_callback = make_log_after_model_call(web_research_agent)

# Create the tool function for use by other agents
web_research_tool = make_run_agent_as_tool_function(
    agent=web_research_agent,
    tool_description="""
    Run the WEB_RESEARCH_AGENT to conduct research using web sources.
    The agent searches the web and retrieves content.

    Use this tool when:
    1. Web-based information gathering is needed
    2. Official sources and authoritative websites should be consulted
    3. News articles and publications need to be researched
    4. Academic and institutional sources are relevant

    Input should be a specific research query for web sources.
    """,
    before_model_callbacks=[web_research_before_callback],
    after_model_callbacks=[web_research_after_callback],
)

# Module exports
__all__ = [
    "web_research_agent",
    "web_research_before_callback",
    "web_research_after_callback",
    "web_research_tool",
]
