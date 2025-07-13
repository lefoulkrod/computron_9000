"""
Analysis Agent for source analysis and credibility assessment.

This module contains the Analysis Agent specialized for performing deep analysis
of sources, credibility assessment, and cross-reference verification.
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
from .analysis_tools import AnalysisTools
from .prompt import ANALYSIS_PROMPT

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Get agent-specific configuration
config = get_agent_config("analysis")
model, options = config.get_model_settings()

# Initialize source tracking for analysis
analysis_source_tracker = AgentSourceTracker(
    agent_id="analysis", shared_registry=SharedSourceRegistry()
)

# Initialize analysis tools with agent-specific source tracker
analysis_tools = AnalysisTools(source_tracker=analysis_source_tracker)

# Define the Analysis Agent
analysis_agent: Agent = Agent(
    name="ANALYSIS_AGENT",
    description="Specialized agent for deep analysis of sources, credibility assessment, cross-reference verification, and inconsistency detection",
    instruction=ANALYSIS_PROMPT,
    model=model,
    options=options,
    tools=[
        analysis_tools.assess_webpage_credibility,
        analysis_tools.extract_webpage_metadata,
        analysis_tools.categorize_source,
        analysis_tools.verify_cross_references,
        analysis_tools.evaluate_source_consistency,
        analysis_tools.perform_comprehensive_credibility_assessment,
        analysis_tools.analyze_reddit_credibility,
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
    "analysis_agent",
    "analysis_before_callback",
    "analysis_after_callback",
    "analysis_tool",
    "analysis_source_tracker",
    "analysis_tools",
]
