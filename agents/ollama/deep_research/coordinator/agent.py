"""
Research Coordinator Agent for multi-agent deep research workflow.

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

from ..shared import get_agent_config
from .coordination_tools import CoordinationTools
from .prompt import RESEARCH_COORDINATOR_PROMPT

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration
config = get_agent_config("coordinator")
model, options = config.get_model_settings()

# Initialize coordination tools
coordination_tools = CoordinationTools("research_coordinator")

# Define the Research Coordinator Agent
research_coordinator_agent: Agent = Agent(
    name="RESEARCH_COORDINATOR_AGENT",
    description="Orchestrates multi-agent research workflows, delegates tasks to specialized agents, and coordinates overall research process",
    instruction=RESEARCH_COORDINATOR_PROMPT,
    model=model,
    options=options,
    tools=[
        coordination_tools.initiate_research_workflow,
        coordination_tools.get_workflow_status,
        coordination_tools.process_agent_result,
        coordination_tools.complete_workflow,
        coordination_tools.execute_agent_task,
        coordination_tools.get_coordination_guidelines,
    ],
)

# Create standard callbacks for logging
research_coordinator_before_callback = make_log_before_model_call(
    research_coordinator_agent
)
research_coordinator_after_callback = make_log_after_model_call(
    research_coordinator_agent
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
    "research_coordinator_agent",
    "research_coordinator_before_callback",
    "research_coordinator_after_callback",
    "research_coordinator_tool",
    "coordination_tools",
]
