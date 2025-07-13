"""
Query Decomposition Agent module.

This module provides the Query Decomposition Agent that analyzes complex
research questions and breaks them into manageable sub-queries.
"""

from .agent import (
    query_decomposition_agent,
    query_decomposition_tool,
)

__all__ = [
    "query_decomposition_agent",
    "query_decomposition_tool",
]
