"""
Deep Research Agent implementation.

This module contains the Deep Research Agent class and associated tool function.
"""

import logging

from agents.types import Agent
from agents.ollama.sdk import (
    make_run_agent_as_tool_function,
    make_log_before_model_call,
    make_log_after_model_call,
)
from config import load_config
from agents.models import get_model_by_name, get_default_model
from .prompt import DEEP_RESEARCH_AGENT_PROMPT

# Load configuration and set up logger
config = load_config()
logger = logging.getLogger(__name__)

# Get model configuration
model = get_default_model()

# Define the agent
deep_research_agent: Agent = Agent(
    name="DEEP_RESEARCH_AGENT",
    description="Specialized agent for conducting thorough research across multiple sources",
    instruction=DEEP_RESEARCH_AGENT_PROMPT,
    model=model.model,
    options=model.options,
    tools=[
        # Tools will be implemented in Phase 2
    ],
)

# Create before and after callbacks for logging
deep_research_agent_before_callback = make_log_before_model_call(deep_research_agent)
deep_research_agent_after_callback = make_log_after_model_call(deep_research_agent)

# Create the tool function for use by other agents
deep_research_agent_tool = make_run_agent_as_tool_function(
    agent=deep_research_agent,
    tool_description="""
    Run the DEEP_RESEARCH_AGENT to conduct comprehensive research on complex topics.
    The agent will search multiple sources, analyze information, verify facts across sources,
    and provide well-documented findings with proper citations.
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
]
