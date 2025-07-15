"""Research Coordinator Agent for multi-agent deep research workflow.

This module contains the Research Coordinator Agent that orchestrates the
multi-agent deep research workflow.
"""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import ModelNotFoundError, get_model_by_name

from .coordination_tools import CoordinationTools
from .prompt import RESEARCH_COORDINATOR_PROMPT

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration from main config
try:
    model_config = get_model_by_name("research_coordinator")
except ModelNotFoundError:
    logger.warning("Research coordinator model not found, falling back to qwen3")
    model_config = get_model_by_name("qwen3")

model = model_config.model
options = model_config.options.copy() if model_config.options else {}

# Initialize coordination tools
coordination_tools = CoordinationTools("research_coordinator")

# Define the Research Coordinator Agent
research_coordinator_agent: Agent = Agent(
    name="RESEARCH_COORDINATOR_AGENT",
    description="Orchestrates automated deep research workflows with single-tool execution",
    instruction=RESEARCH_COORDINATOR_PROMPT,
    model=model,
    options=options,
    tools=[
        coordination_tools.execute_deep_research_workflow,
        coordination_tools.cleanup_completed_tasks,
    ],
)

# Create standard callbacks for logging
research_coordinator_before_callback = make_log_before_model_call(
    research_coordinator_agent,
)
research_coordinator_after_callback = make_log_after_model_call(
    research_coordinator_agent,
)

# Create the tool function for use by other agents
research_coordinator_tool = make_run_agent_as_tool_function(
    agent=research_coordinator_agent,
    tool_description="""
    Run the RESEARCH_COORDINATOR_AGENT to orchestrate comprehensive multi-agent research workflows.
    The coordinator delegates specialized tasks to different research agents and combines their results.

    Use this tool when:
    1. Complex research requiring multiple specialized agents
    2. Coordination of parallel research tasks is needed
    3. Synthesis of findings from different research domains is required

    Input should be a comprehensive research query.
    """,
    before_model_callbacks=[research_coordinator_before_callback],
    after_model_callbacks=[research_coordinator_after_callback],
)

# Module exports
__all__ = [
    "coordination_tools",
    "research_coordinator_after_callback",
    "research_coordinator_agent",
    "research_coordinator_before_callback",
    "research_coordinator_tool",
]
