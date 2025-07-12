"""
Deep Research Agent implementation.

This module contains the Deep Research Agent class and associated tool function.
"""

import logging
import time
from typing import Dict, Any, List, Optional, Callable, Union

from agents.types import Agent
from agents.ollama.sdk import (
    make_run_agent_as_tool_function,
    make_log_before_model_call,
    make_log_after_model_call,
    LLMRuntimeStats,
)
from ollama import ChatResponse, GenerateResponse
from config import load_config
from agents.models import get_model_by_name, get_default_model
from tools.web import (
    search_google, 
    get_webpage, 
    get_webpage_summary,
    html_find_elements,
)
from tools.reddit import (
    search_reddit,
    get_reddit_comments_tree_shallow,
)
from .prompt import DEEP_RESEARCH_AGENT_PROMPT
from .types import ResearchReport, ResearchSource

# Load configuration and set up logger
config = load_config()
logger = logging.getLogger(__name__)

# Get model configuration for Deep Research Agent
try:
    # Try to get the dedicated deep_research model
    model = get_model_by_name("deep_research")
    logger.info(f"Using dedicated deep_research model: {model.model}")
except Exception:
    # Fall back to default model if the dedicated one isn't found
    model = get_default_model()
    logger.info(f"Using default model {model.model} for Deep Research Agent")

# No custom callbacks - using standard logging provided by SDK

# Define the agent with enhanced capabilities
deep_research_agent: Agent = Agent(
    name="DEEP_RESEARCH_AGENT",
    description="Specialized agent for conducting thorough research across multiple sources to provide comprehensive, well-sourced answers to complex queries",
    instruction=DEEP_RESEARCH_AGENT_PROMPT,
    model=model.model,
    options=model.options,  # Using the options from the dedicated model configuration
    tools=[
        # Web research tools
        search_google,
        get_webpage,
        get_webpage_summary,
        html_find_elements,
        
        # Reddit research tools
        search_reddit,
        get_reddit_comments_tree_shallow,
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
]
