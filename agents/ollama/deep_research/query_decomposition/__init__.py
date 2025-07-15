"""Query Decomposition Agent module.

This module provides the Query Decomposition Agent that analyzes complex
research questions and breaks them into manageable sub-queries.

This module is internal to the deep_research package.
"""

# Internal imports only - not exposed outside deep_research package
from .agent import (
    query_decomposition_agent,
    query_decomposition_tool,
)

# No public exports - this is an internal module
