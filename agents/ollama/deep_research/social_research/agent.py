"""
Social Research Agent for social media and forum research.

This module contains the Social Research Agent specialized for conducting
research using social media and forum sources.
"""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from tools.reddit import get_reddit_comments_tree_shallow, search_reddit

from ..shared import get_agent_config
from .prompt import SOCIAL_RESEARCH_PROMPT

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration
config = get_agent_config("social_research")
model, options = config.get_model_settings()

# Define the Social Research Agent
social_research_agent: Agent = Agent(
    name="SOCIAL_RESEARCH_AGENT",
    description="Specialized agent for conducting research using social media and forum sources",
    instruction=SOCIAL_RESEARCH_PROMPT,
    model=model,
    options=options,
    tools=[
        search_reddit,
        get_reddit_comments_tree_shallow,
    ],
)

# Create standard callbacks for logging
social_research_before_callback = make_log_before_model_call(social_research_agent)
social_research_after_callback = make_log_after_model_call(social_research_agent)

# Create the tool function for use by other agents
social_research_tool = make_run_agent_as_tool_function(
    agent=social_research_agent,
    tool_description="""
    Run the SOCIAL_RESEARCH_AGENT to conduct research using social media and forum sources.
    The agent searches social platforms and retrieves discussions.

    Use this tool when:
    1. Community discussions and forums should be analyzed
    2. Social media content is relevant to research
    3. User perspectives and experiences are important

    Input should be a specific research query for social sources.
    """,
    before_model_callbacks=[social_research_before_callback],
    after_model_callbacks=[social_research_after_callback],
)

# Module exports
__all__ = [
    "social_research_agent",
    "social_research_before_callback",
    "social_research_after_callback",
    "social_research_tool",
]
