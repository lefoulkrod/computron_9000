"""
Web Research Agent for web-based research tasks.

This module contains the Web Research Agent specialized for conducting
research using web sources with source tracking and credibility assessment.
"""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent

from ..shared import (
    AgentSourceTracker,
    SharedSourceRegistry,
    get_agent_config,
)
from .prompt import WEB_RESEARCH_PROMPT
from .web_tools import WebResearchTools

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration
config = get_agent_config("web_research")
model, options = config.get_model_settings()

# Initialize source tracking for web research
web_source_tracker = AgentSourceTracker(
    agent_id="web_research",
    shared_registry=SharedSourceRegistry()
)

# Initialize web research tools with agent-specific source tracker
web_tools = WebResearchTools(source_tracker=web_source_tracker)

# Define the Web Research Agent
web_research_agent: Agent = Agent(
    name="WEB_RESEARCH_AGENT",
    description="Specialized agent for conducting research using web sources with automatic source tracking and credibility assessment",
    instruction=WEB_RESEARCH_PROMPT,
    model=model,
    options=options,
    tools=[
        web_tools.search_google,
        web_tools.get_webpage,
        web_tools.get_webpage_summary,
        web_tools.get_webpage_summary_sections,
        web_tools.get_webpage_substring,
        web_tools.html_find_elements,
        web_tools.assess_webpage_credibility,
        web_tools.extract_webpage_metadata,
        web_tools.categorize_source,
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
    The agent searches the web, retrieves content, and assesses source credibility.

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
    "web_source_tracker",
    "web_tools",
]
