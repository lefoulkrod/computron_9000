"""
Synthesis Agent for combining findings and generating reports.

This module contains the Synthesis Agent specialized for synthesizing information
from multiple sources and generating comprehensive research reports.
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
from .prompt import SYNTHESIS_PROMPT

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration
config = get_agent_config("synthesis")
model, options = config.get_model_settings()

# Initialize source tracking for synthesis
synthesis_source_tracker = AgentSourceTracker(
    agent_id="synthesis",
    shared_registry=SharedSourceRegistry()
)

# Define the Synthesis Agent
synthesis_agent: Agent = Agent(
    name="SYNTHESIS_AGENT",
    description="Specialized agent for synthesizing information from multiple sources and generating comprehensive research reports with citations",
    instruction=SYNTHESIS_PROMPT,
    model=model,
    options=options,
    tools=[
        # Synthesis tools will be implemented in Phase 3.2
    ],
)

# Create standard callbacks for logging
synthesis_before_callback = make_log_before_model_call(synthesis_agent)
synthesis_after_callback = make_log_after_model_call(synthesis_agent)

# Create the tool function for use by other agents
synthesis_tool = make_run_agent_as_tool_function(
    agent=synthesis_agent,
    tool_description="""
    Run the SYNTHESIS_AGENT to synthesize research findings into comprehensive reports.
    The agent combines information from multiple sources and creates structured reports with citations.

    Use this tool when:
    1. Multiple research findings need to be combined
    2. Comprehensive reports with citations are required
    3. Knowledge gaps and contradictions need to be identified
    4. Final research summaries are needed

    Input should be research findings from multiple agents and sources.
    """,
    before_model_callbacks=[synthesis_before_callback],
    after_model_callbacks=[synthesis_after_callback],
)

# Module exports
__all__ = [
    "synthesis_agent",
    "synthesis_before_callback",
    "synthesis_after_callback",
    "synthesis_tool",
]
