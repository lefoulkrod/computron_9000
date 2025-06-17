"""Definition of the COMPUTRON_9000 LLM agent using Pydantic AI API (decorator-based tools, async)."""

import logging
from typing import Any, List, Optional

from config import load_config
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.messages import ModelMessage
from collections.abc import Coroutine
from pydantic_ai.agent import AgentRunResult

from .file_system import run_file_system_agent
from agents.prompt import ROOT_AGENT_PROMPT
from tools.misc.datetime import datetime_tool, DateTimeResult
from tools.web.get_webpage import get_webpage, GetWebpageError, GetWebpageResult
from tools.web.search_google import search_google, GoogleSearchError, GoogleSearchResults

config = load_config()
ollama_model = OpenAIModel(
    model_name=config.llm.model,
    provider=OpenAIProvider(
        base_url="http://localhost:11434/v1",
    ),
    system_prompt_role="system",
)

computron_agent = Agent(
    model=ollama_model,
    system_prompt=ROOT_AGENT_PROMPT,
)

logger = logging.getLogger(__name__)

@computron_agent.tool
async def file_system(ctx: RunContext[None], user_input: str) -> Any:
    """
    Call the file system agent with the given user input.

    Args:
        ctx (RunContext[None]): The agent run context.
        user_input (str): The user's request or command for the file system agent.

    Returns:
        Any: The file system agent's response.
    """
    return await run_file_system_agent(user_input, ctx)

@computron_agent.tool_plain
def get_datetime() -> DateTimeResult:
    """
    Get the current system date and time in human-readable 12-hour format (up to seconds).

    Args:
        ctx (RunContext[None]): The agent run context (unused).

    Returns:
        DateTimeResult: Result object containing the formatted date and time string, or error details.
    """
    return datetime_tool()

@computron_agent.tool
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
        logger.error(f"get_webpage tool error: {e}")
        raise

async def run_computron_agent(
    user_input: str,
    message_history: Optional[List[ModelMessage]] = None
) -> AgentRunResult[str] | None:
    """
    Run the COMPUTRON_9000 agent asynchronously with the given user input and optional message history.

    Args:
        user_input (str): The user's request or command.
        message_history (Optional[List[ModelMessage]]): The message history to provide as context.

    Returns:
        AgentRunResult[str] | None: The agent's result object (not just output), or None if an error occurs.
    """
    try:
        if message_history is not None:
            result = await computron_agent.run(user_input, message_history=message_history)
        else:
            result = await computron_agent.run(user_input)
        return result
    except Exception as exc:
        logger.error(f"COMPUTRON_9000 agent error: {exc}")
        return None