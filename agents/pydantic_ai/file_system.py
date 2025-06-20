"""File system agent using Pydantic AI API (decorator-based tools, async)."""

import logging
from typing import Any

from pydantic_ai import Agent, RunContext
from config import load_config
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from agents.prompt import FILE_SYSTEM_AGENT_PROMPT
from tools.fs.fs import (
    list_directory_contents,
    get_path_details,
    read_file_contents,
    search_files,
)

logger = logging.getLogger(__name__)

config = load_config()

ollama_model = OpenAIModel(
    model_name=config.llm.model,
    provider=OpenAIProvider(
        base_url="http://localhost:11434/v1",
    ),
    system_prompt_role="system",
)

file_system_agent = Agent(
    model=ollama_model,
    system_prompt=FILE_SYSTEM_AGENT_PROMPT,
    tools=[
        list_directory_contents,
        get_path_details,
        read_file_contents,
        search_files,
    ],
)

async def run_file_system_agent(ctx: RunContext[None], user_input: str) -> Any:
    """
    Execute file system operations as a tool callable by other agents.

    This function exposes the file system agent as an async tool for use by other agents, enabling them to perform directory listings, file detail inspection, file reading, and file searching. It is designed for seamless integration into multi-agent workflows, allowing agents to delegate file system tasks and receive structured results.

    Args:
        user_input (str): The file system-related request or command from another agent.
        ctx (RunContext[None]): The agent run context, including usage tracking and metadata.

    Returns:
        Any: The agent's structured response to the file system operation, or an error message if the operation fails.

    Raises:
        Logs and returns an error dictionary if an exception occurs during execution.
    """
    try:
        result = await file_system_agent.run(user_input, usage=ctx.usage)
        return result.output
    except Exception as exc:
        logger.error(f"FileSystem agent error: {exc}")
        return {"error": str(exc)}
