"""
Synthesis Agent module.

This module provides the Synthesis Agent specialized for synthesizing information
from multiple sources and generating comprehensive research reports.
"""

from .agent import (
    synthesis_after_callback,
    synthesis_agent,
    synthesis_before_callback,
    synthesis_tool,
)
from .synthesis_tools import (
    create_citation_list,
    create_executive_summary,
    generate_bibliography,
    generate_research_report,
    identify_knowledge_gaps,
    resolve_contradictions,
    synthesize_multi_source_findings,
)

__all__ = [
    "synthesis_agent",
    "synthesis_before_callback",
    "synthesis_after_callback",
    "synthesis_tool",
    "synthesize_multi_source_findings",
    "generate_research_report",
    "create_citation_list",
    "generate_bibliography",
    "identify_knowledge_gaps",
    "resolve_contradictions",
    "create_executive_summary",
]
