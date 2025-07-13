"""
Query Decomposition Agent module.

This module provides the Query Decomposition Agent that analyzes complex
research questions and breaks them into manageable sub-queries.
"""

from .agent import (
    query_decomposition_after_callback,
    query_decomposition_agent,
    query_decomposition_before_callback,
    query_decomposition_tool,
)
from .decomposer import (
    analyze_query_complexity,
    decompose_research_query,
    identify_query_dependencies,
    prioritize_sub_queries,
)

__all__ = [
    "query_decomposition_agent",
    "query_decomposition_before_callback",
    "query_decomposition_after_callback",
    "query_decomposition_tool",
    "analyze_query_complexity",
    "decompose_research_query",
    "identify_query_dependencies",
    "prioritize_sub_queries",
]
