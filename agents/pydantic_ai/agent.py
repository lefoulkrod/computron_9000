import logging
from typing import Any

from tools.web.get_webpage import get_webpage, GetWebpageError, GetWebpageResult
from pydantic_ai import Agent, RunContext

# Example: Register get_webpage as a tool for the agent
async def get_webpage_tool(ctx: RunContext[None], url: str) -> GetWebpageResult:
    """
    Navigate to a webpage and return its HTML content using Playwright.

    Args:
        ctx (RunContext[None]): The agent run context.
        url (str): The URL to get.

    Returns:
        GetWebpageResult: The result containing the URL and HTML content.

    Raises:
        GetWebpageError: If navigation or fetching fails.
    """
    try:
        return await get_webpage(url)
    except GetWebpageError as e:
        logging.error(f"get_webpage tool error: {e}")
        raise

# To register this tool with your agent, add a decorator in your agent definition file (e.g., computron.py)
# Example:
# @your_agent.tool
# async def get_webpage_tool(ctx: RunContext[None], url: str) -> GetWebpageResult:
#     ...