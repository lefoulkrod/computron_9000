"""
Query Decomposition Agent for breaking down complex research queries.

This module contains the Query Decomposition Agent that analyzes complex
research questions and breaks them into manageable sub-queries.
"""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import ModelNotFoundError, get_model_by_name

from ..shared.agent_task_tools import get_query_decomposition_task_data
from .decomposer import QueryDecomposer
from .prompt import QUERY_DECOMPOSITION_PROMPT

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration from main config
# Fallback to qwen3 if specific model not found
try:
    model_config = get_model_by_name("query_decomposition")
except ModelNotFoundError:
    logger.warning("Query decomposition model not found, falling back to qwen3")
    model_config = get_model_by_name("qwen3")

model = model_config.model
options = model_config.options.copy() if model_config.options else {}

# Initialize query decomposition tools
# Note: The QueryDecomposer will be used for implementation logic
# but for now we'll integrate tools in the agent definition
decomposer = QueryDecomposer()  # Initialize without source tracker for now

# Define the Query Decomposition Agent
query_decomposition_agent: Agent = Agent(
    name="QUERY_DECOMPOSITION_AGENT",
    description="Analyzes complex research questions and breaks them down into manageable sub-queries with prioritized research plans",
    instruction=QUERY_DECOMPOSITION_PROMPT,
    model=model,
    options=options,
    tools=[
        get_query_decomposition_task_data,
        # Additional tools will be added in future implementation phases
        # For now, the agent provides query decomposition through conversation
    ],
)

# Create standard callbacks for logging
query_decomposition_before_callback = make_log_before_model_call(
    query_decomposition_agent
)
query_decomposition_after_callback = make_log_after_model_call(
    query_decomposition_agent
)

# Create the tool function for use by other agents
query_decomposition_tool = make_run_agent_as_tool_function(
    agent=query_decomposition_agent,
    tool_description="""
    Run the QUERY_DECOMPOSITION_AGENT to break down complex research queries into manageable sub-queries.
    The agent analyzes research questions and creates prioritized research plans.

    Use this tool when:
    1. Complex research queries need to be broken down
    2. Research strategy planning is required
    3. Sub-query prioritization is needed
    4. Research dependencies need identification

    Input should be a complex research query or topic.

    The agent will provide:
    - Analysis of query complexity and scope
    - Breakdown into specific sub-queries
    - Dependency relationships between sub-queries
    - Prioritized execution order
    - Research strategy recommendations
    """,
    before_model_callbacks=[query_decomposition_before_callback],
    after_model_callbacks=[query_decomposition_after_callback],
)

# Module exports
__all__ = [
    "query_decomposition_agent",
    "query_decomposition_before_callback",
    "query_decomposition_after_callback",
    "query_decomposition_tool",
    "decomposer",
]
