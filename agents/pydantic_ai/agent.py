import logging
from typing import Any

from tools.web.open_webpage import open_webpage, OpenWebpageError, OpenWebpageResult
from pydantic_ai import Agent, RunContext

# Example: Register open_webpage as a tool for the agent
async def open_webpage_tool(ctx: RunContext[None], url: str) -> OpenWebpageResult:
    """
    Navigate to a webpage and return its HTML content using Playwright.

    Args:
        ctx (RunContext[None]): The agent run context.
        url (str): The URL to open.

    Returns:
        OpenWebpageResult: The result containing the URL and HTML content.

    Raises:
        OpenWebpageError: If navigation or fetching fails.
    """
    try:
        return await open_webpage(url)
    except OpenWebpageError as e:
        logging.error(f"open_webpage tool error: {e}")
        raise

# To register this tool with your agent, add a decorator in your agent definition file (e.g., computron.py)
# Example:
# @your_agent.tool
# async def open_webpage_tool(ctx: RunContext[None], url: str) -> OpenWebpageResult:
#     ...