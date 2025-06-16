"""Definition of the COMPUTRON_9000 LLM agent using Pydantic AI API (decorator-based tools, async)."""

import logging
from typing import Any, List, Optional

from config import load_config
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.messages import ModelMessage

from .file_system import run_file_system_agent
from agents.prompt import ROOT_AGENT_PROMPT

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

async def run_computron_agent(user_input: str, message_history: Optional[List[ModelMessage]] = None) -> Any:
    """
    Run the COMPUTRON_9000 agent asynchronously with the given user input and optional message history.

    Args:
        user_input (str): The user's request or command.
        message_history (Optional[List[ModelMessage]]): The message history to provide as context.

    Returns:
        Any: The agent's result object (not just output).
    """
    try:
        if message_history is not None:
            result = await computron_agent.run(user_input, message_history=message_history)
        else:
            result = await computron_agent.run(user_input)
        return result
    except Exception as exc:
        logging.error(f"COMPUTRON_9000 agent error: {exc}")
        return None