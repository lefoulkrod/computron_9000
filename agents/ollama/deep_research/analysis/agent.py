"""Analysis Agent for source analysis and credibility assessment.

This module contains the Analysis Agent specialized for performing analysis
of sources using basic web research tools.
"""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import ModelNotFoundError, get_model_by_name
from tools.web import (
    get_webpage,
    get_webpage_substring,
    get_webpage_summary,
    get_webpage_summary_sections,
    html_find_elements,
    search_google,
)

from ..shared.agent_task_tools import get_analysis_task_data
from .prompt import ANALYSIS_PROMPT

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration from main config
try:
    model_config = get_model_by_name("analysis")
except ModelNotFoundError:
    logger.warning("Analysis model not found, falling back to qwen3")
    model_config = get_model_by_name("qwen3")

model = model_config.model
options = model_config.options.copy() if model_config.options else {}

# Define the Analysis Agent
analysis_agent: Agent = Agent(
    name="ANALYSIS_AGENT",
    description="Specialized agent for analysis of sources using web research tools",
    instruction=ANALYSIS_PROMPT,
    model=model,
    options=options,
    tools=[
        get_analysis_task_data,
        search_google,
        get_webpage,
        get_webpage_summary,
        get_webpage_summary_sections,
        get_webpage_substring,
        html_find_elements,
    ],
)

# Create standard callbacks for logging
analysis_before_callback = make_log_before_model_call(analysis_agent)
analysis_after_callback = make_log_after_model_call(analysis_agent)

# Create the tool function for use by other agents
analysis_tool = make_run_agent_as_tool_function(
    agent=analysis_agent,
    tool_description="""
    Run the ANALYSIS_AGENT to perform deep analysis of sources and information.
    The agent assesses credibility, verifies cross-references, and detects inconsistencies.

    Use this tool when:
    1. Source credibility assessment is needed
    2. Cross-reference verification is required
    3. Inconsistency detection between sources is important
    4. Metadata extraction and analysis is needed

    Input should be sources and information to analyze.
    """,
    before_model_callbacks=[analysis_before_callback],
    after_model_callbacks=[analysis_after_callback],
)

# Module exports
__all__ = [
    "analysis_after_callback",
    "analysis_agent",
    "analysis_before_callback",
    "analysis_tool",
]
