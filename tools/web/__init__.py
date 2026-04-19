"""Web utilities package exposing HTML fetching and summarization helpers.

This package contains tools used to fetch webpages, extract visible text, and
generate summaries used elsewhere in the project.
"""

from .get_webpage import (
    get_webpage,
    get_webpage_substring,
    get_webpage_summary,
    get_webpage_summary_sections,
)
from .html_find_elements import HtmlElementResult, html_find_elements
from .types import GetWebpageError, GetWebpageResult

__all__ = [
    "GetWebpageError",
    "GetWebpageResult",
    "HtmlElementResult",
    "get_webpage",
    "get_webpage_substring",
    "get_webpage_summary",
    "get_webpage_summary_sections",
    "html_find_elements",
]
