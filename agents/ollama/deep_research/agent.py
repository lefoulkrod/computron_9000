"""
Deep Research Agent implementation.

This module contains the Deep Research Agent class and associated tool function.
"""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from config import load_config
from models import get_model_by_name

from .prompt import DEEP_RESEARCH_AGENT_PROMPT
from .source_tracker import SourceTracker
from .tools import (
    get_citation_practices,
    get_tool_documentation,
    search_tool_documentation,
)
from .tracked_tools import get_tracked_reddit_tools, get_tracked_web_tools

# Load configuration and set up logger
config = load_config()
logger = logging.getLogger(__name__)

# Initialize source tracker
source_tracker = SourceTracker()

model = get_model_by_name("deep_research")

# Get tracked tools with source tracking capability
tracked_web_tools = get_tracked_web_tools(source_tracker)
tracked_reddit_tools = get_tracked_reddit_tools(source_tracker)

# Define the agent with enhanced capabilities
deep_research_agent: Agent = Agent(
    name="DEEP_RESEARCH_AGENT",
    description="Specialized agent for conducting thorough research across multiple sources to provide comprehensive, well-sourced answers to complex queries",
    instruction=DEEP_RESEARCH_AGENT_PROMPT,
    model=model.model,
    options=model.options,  # Using the options from the dedicated model configuration
    tools=[
        # Web research tools with source tracking
        tracked_web_tools["search_google"],
        tracked_web_tools["get_webpage"],
        tracked_web_tools["get_webpage_summary"],
        tracked_web_tools["get_webpage_summary_sections"],
        tracked_web_tools["get_webpage_substring"],
        tracked_web_tools["html_find_elements"],
        tracked_web_tools["assess_webpage_credibility"],
        tracked_web_tools["extract_webpage_metadata"],
        tracked_web_tools["categorize_source"],
        # Reddit research tools with source tracking
        tracked_reddit_tools["search_reddit"],
        tracked_reddit_tools["get_reddit_comments_tree_shallow"],
        tracked_reddit_tools["analyze_reddit_credibility"],
        tracked_reddit_tools["analyze_comment_sentiment"],
        # Tool documentation access
        get_tool_documentation,
        search_tool_documentation,
        get_citation_practices,
    ],
)

# Create standard callbacks for logging
deep_research_agent_before_callback = make_log_before_model_call(deep_research_agent)
deep_research_agent_after_callback = make_log_after_model_call(deep_research_agent)

# Create the tool function for use by other agents
deep_research_agent_tool = make_run_agent_as_tool_function(
    agent=deep_research_agent,
    tool_description="""
    Run the DEEP_RESEARCH_AGENT to conduct comprehensive research on complex topics.
    The agent will search multiple sources, analyze information, verify facts across sources,
    and provide well-documented findings with proper citations.

    Use this tool when:
    1. The user needs in-depth research on a complex topic
    2. Information needs to be gathered from multiple sources
    3. Facts need to be verified across different references
    4. A comprehensive report with proper citations is required

    Input should be a specific research query or topic.
    """,
    before_model_callbacks=[deep_research_agent_before_callback],
    after_model_callbacks=[deep_research_agent_after_callback],
)

# Module exports
__all__ = [
    "deep_research_agent",
    "deep_research_agent_before_callback",
    "deep_research_agent_after_callback",
    "deep_research_agent_tool",
    "source_tracker",
    "get_tool_documentation",
    "search_tool_documentation",
    "get_citation_practices",
]
