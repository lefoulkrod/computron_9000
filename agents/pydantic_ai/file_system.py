"""File system agent using Pydantic AI API (decorator-based tools, async)."""

import logging
from typing import Any

from pydantic_ai import Agent, RunContext
from config import load_config
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from agents.prompt import FILE_SYSTEM_AGENT_PROMPT
from tools.fs import (
    list_directory_contents,
    get_path_details,
    read_file_contents,
    search_files,
    write_text_file,
)

logger = logging.getLogger(__name__)

config = load_config()

ollama_model = OpenAIModel(
    model_name=config.llm.model,
    provider=OpenAIProvider(
        base_url="http://localhost:11434/v1",
    ),
)

file_system_agent = Agent(
    model=ollama_model,
    instructions=FILE_SYSTEM_AGENT_PROMPT,
    tools=[
        list_directory_contents,
        get_path_details,
        read_file_contents,
        search_files,
        write_text_file
    ],
)

async def run_file_system_agent(ctx: RunContext[None], instructions: str) -> Any:
    """
    Execute file system operations as a tool callable by other agents.

    This function exposes the file system agent as an async tool for use by other agents, enabling them to perform all common file system operations. Callers should provide detailed, step-by-step instructions describing the specific file system tasks or workflows they want the agent to perform. When reading or writing files, always specify the exact filename. This design allows seamless integration into multi-agent workflows, enabling agents to delegate file system tasks and receive structured results.

    Args:
        instructions (str): The file system-related request or command from another agent.
        ctx (RunContext[None]): The agent run context, including usage tracking and metadata.

    Returns:
        Any: The agent's structured response to the file system operation, or an error message if the operation fails.

    Raises:
        Logs and returns an error dictionary if an exception occurs during execution.
    """
    agent_input = instructions
    if not config.agents.file_system.think:
        agent_input = instructions + " /no_think"
    logger.debug(f"Running file system agent with instructions: {agent_input}")
    try:
        result = await file_system_agent.run(agent_input, usage=ctx.usage)
        return result.output
    except Exception as exc:
        logger.error(f"FileSystem agent error: {exc}")
        return {"error": str(exc)}
