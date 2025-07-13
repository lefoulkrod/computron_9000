"""
Social Research Agent for social media and forum research.

This module contains the Social Research Agent specialized for conducting
research using social media and forum sources with sentiment analysis.
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
from .prompt import SOCIAL_RESEARCH_PROMPT
from .social_tools import SocialResearchTools

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration
config = get_agent_config("social_research")
model, options = config.get_model_settings()

# Initialize source tracking for social research
social_source_tracker = AgentSourceTracker(
    agent_id="social_research",
    shared_registry=SharedSourceRegistry()
)

# Initialize social research tools with agent-specific source tracker
social_tools = SocialResearchTools(source_tracker=social_source_tracker)

# Define the Social Research Agent
social_research_agent: Agent = Agent(
    name="SOCIAL_RESEARCH_AGENT",
    description="Specialized agent for conducting research using social media and forum sources with sentiment analysis and credibility assessment",
    instruction=SOCIAL_RESEARCH_PROMPT,
    model=model,
    options=options,
    tools=[
        social_tools.search_reddit,
        social_tools.get_reddit_comments_tree_shallow,
        social_tools.analyze_reddit_credibility,
        social_tools.analyze_comment_sentiment,
        social_tools.analyze_comment_sentiment_basic,
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
    The agent searches social platforms, analyzes discussions, and assesses public sentiment.

    Use this tool when:
    1. Public opinion and sentiment analysis is needed
    2. Community discussions and forums should be analyzed
    3. Social media trends and reactions are relevant
    4. Grassroots perspectives and user experiences are important

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
    "social_source_tracker",
    "social_tools",
]
