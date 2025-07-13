"""
Deep Research Agent implementation.

This module contains the Deep Research Agent class and associated tool function.
This is the legacy single-agent interface that maintains backward compatibility
while internally using the new multi-agent infrastructure.
"""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent

from .backward_compatibility import (
    LegacyAgentConfig,
    create_legacy_source_tracker,
    get_legacy_tracked_tools,
)
from .inter_agent_communication import (
    check_multi_agent_workflow_status,
    delegate_to_multi_agent_research,
    get_multi_agent_capabilities,
)
from .prompt import DEEP_RESEARCH_AGENT_PROMPT
from .tools import (
    get_citation_practices,
    get_tool_documentation,
    search_tool_documentation,
)

# Load configuration and set up logger
logger = logging.getLogger(__name__)

# Use legacy configuration for backward compatibility
legacy_config = LegacyAgentConfig()

# Initialize legacy source tracker (maintains backward compatibility)
source_tracker = create_legacy_source_tracker()

# Get tracked tools with legacy interface
tracked_tools = get_legacy_tracked_tools(source_tracker)

# Extract specific tool categories for readability
tracked_web_tools = {
    k: v
    for k, v in tracked_tools.items()
    if k
    in [
        "search_google",
        "get_webpage",
        "get_webpage_summary",
        "get_webpage_summary_sections",
        "get_webpage_substring",
        "html_find_elements",
        "assess_webpage_credibility",
        "extract_webpage_metadata",
        "categorize_source",
    ]
}

tracked_reddit_tools = {
    k: v
    for k, v in tracked_tools.items()
    if k
    in [
        "search_reddit",
        "get_reddit_comments_tree_shallow",
        "analyze_reddit_credibility",
        "analyze_comment_sentiment",
    ]
}

# Define the agent with enhanced capabilities (legacy interface)
deep_research_agent: Agent = Agent(
    name="DEEP_RESEARCH_AGENT",
    description="Specialized agent for conducting thorough research across multiple sources to provide comprehensive, well-sourced answers to complex queries",
    instruction=DEEP_RESEARCH_AGENT_PROMPT,
    model=legacy_config.model,
    options=legacy_config.options,
    tools=[
        delegate_to_multi_agent_research,
        check_multi_agent_workflow_status,
        get_multi_agent_capabilities,
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
    "source_tracker",
    "get_tool_documentation",
    "search_tool_documentation",
    "get_citation_practices",
]
