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
)

logger = logging.getLogger(__name__)

@file_system_agent.tool_plain
def list_dir(path: str) -> Any:
    """List files and directories at a given path."""
    try:
        return list_directory_contents(path)
    except Exception as exc:
        logger.error(f"list_directory_contents error: {exc}")
        return {"status": "error", "contents": [], "error_message": str(exc)}

@file_system_agent.tool_plain
def path_details(path: str) -> Any:
    """Get details about a filesystem path."""
    try:
        return get_path_details(path)
    except Exception as exc:
        logger.error(f"get_path_details error: {exc}")
        return {"status": "error", "details": {}, "error_message": str(exc)}

@file_system_agent.tool_plain
def read_file(path: str) -> Any:
    """Read the contents of a file."""
    try:
        return read_file_contents(path)
    except Exception as exc:
        logger.error(f"read_file_contents error: {exc}")
        return {"status": "error", "contents": "", "error_message": str(exc)}

@file_system_agent.tool_plain
def search(pattern: str) -> Any:
    """Search for files matching a glob pattern."""
    try:
        return search_files(pattern)
    except Exception as exc:
        logger.error(f"search_files error: {exc}")
        return {"status": "error", "matches": [], "error_message": str(exc)}

async def run_file_system_agent(user_input: str, ctx: RunContext[None]) -> Any:
    """
    Run the file system agent asynchronously with the given user input.

    Args:
        user_input (str): The user's request or command.
        ctx (RunContext[None]): The agent run context.

    Returns:
        Any: The agent's response.
    """
    try:
        result = await file_system_agent.run(user_input, usage=ctx.usage)
        return result.output
    except Exception as exc:
        logger.error(f"FileSystem agent error: {exc}")
        return {"error": str(exc)}
