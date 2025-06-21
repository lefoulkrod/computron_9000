"""Web agent using Pydantic AI API (decorator-based tools, async)."""

import logging
from typing import Any

from pydantic_ai import Agent, RunContext
from config import load_config
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from agents.prompt import WEB_AGENT_PROMPT
from tools.web.get_webpage import get_webpage
from tools.web.search_google import search_google
from tools.code.execute_code import execute_nodejs_program_with_playwright

logger = logging.getLogger(__name__)

config = load_config()

ollama_model = OpenAIModel(
    model_name=config.llm.model,
    provider=OpenAIProvider(
        base_url="http://localhost:11434/v1",
    ),
    system_prompt_role="system",
)

web_agent = Agent(
    model=ollama_model,
    system_prompt=WEB_AGENT_PROMPT,
    tools=[
        get_webpage,
        execute_nodejs_program_with_playwright,
    ],
)

async def run_web_agent(ctx: RunContext[None], user_input: str) -> Any:
    """
    Execute web navigation, search, and extraction tasks as a tool callable by other agents.

    This function exposes the web agent as an async tool for use by other agents, enabling them to perform web search, navigation, and multi-step workflows. It is designed for seamless integration into multi-agent workflows, allowing agents to delegate web tasks and receive structured results.

    Args:
        user_input (str): The web-related request or command from another agent.
        ctx (RunContext[None]): The agent run context, including usage tracking and metadata.

    Returns:
        Any: The agent's structured response to the web operation, or an error message if the operation fails.

    Raises:
        Logs and returns an error dictionary if an exception occurs during execution.
    """
    try:
        result = await web_agent.run(user_input, usage=ctx.usage)
        return result.output
    except Exception as exc:
        logger.error(f"Web agent error: {exc}", exc_info=True)
        return {"error": str(exc)}
