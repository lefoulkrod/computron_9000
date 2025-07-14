"""
Synthesis Agent for combining findings and generating reports.

This module contains the Synthesis Agent specialized for synthesizing information
from multiple sources and generating research reports.
"""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent

from ..shared import get_agent_config
from ..shared.agent_task_tools import get_task_data
from .prompt import SYNTHESIS_PROMPT
from .synthesis_tools import synthesize_multi_source_findings

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration
config = get_agent_config("synthesis")
model, options = config.get_model_settings()

# Define the Synthesis Agent
synthesis_agent: Agent = Agent(
    name="SYNTHESIS_AGENT",
    description="Specialized agent for synthesizing information from multiple sources and generating research reports",
    instruction=SYNTHESIS_PROMPT,
    model=model,
    options=options,
    tools=[
        get_task_data,
        synthesize_multi_source_findings,
    ],
)

# Create standard callbacks for logging
synthesis_before_callback = make_log_before_model_call(synthesis_agent)
synthesis_after_callback = make_log_after_model_call(synthesis_agent)

# Create tool function for use by other agents
synthesis_tool = make_run_agent_as_tool_function(
    agent=synthesis_agent,
    tool_description="""
    Run the SYNTHESIS_AGENT to synthesize information from multiple sources and generate comprehensive research reports.
    The agent combines findings, creates citations, builds knowledge graphs, and identifies gaps.

    Use this tool when:
    1. Multiple research findings need to be synthesized into a coherent report
    2. Citation lists and bibliographies are needed
    3. Knowledge graphs should be built from research data
    4. Knowledge gaps and contradictions need identification
    5. Comprehensive research reports are required

    Input should include research findings from multiple agents and sources.
    The agent will return synthesized information, reports, and analysis.
    """,
    before_model_callbacks=[synthesis_before_callback],
    after_model_callbacks=[synthesis_after_callback],
)

# Create the tool function for use by other agents
synthesis_tool = make_run_agent_as_tool_function(
    agent=synthesis_agent,
    tool_description="""
    Run the SYNTHESIS_AGENT to synthesize research findings into comprehensive reports.
    The agent combines information from multiple sources and creates structured reports.

    Use this tool when:
    1. Multiple research findings need to be combined
    2. Research summaries are needed
    3. Information from different sources needs to be organized

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
