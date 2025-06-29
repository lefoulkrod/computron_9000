"""Definition of the COMPUTRON_9000 LLM agent using Pydantic AI API (decorator-based tools, async)."""

import logging
from typing import List, Optional


from pydantic_ai import Agent, Tool
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from agents.prompt import ROOT_AGENT_PROMPT
from config import load_config
from tools.code.execute_code import (
    execute_python_program,
)
from tools.code.execute_code import execute_nodejs_program
from tools.misc.datetime import datetime_tool
from .file_system import run_file_system_agent
from .web import run_web_agent

logger = logging.getLogger(__name__)

config = load_config()

ollama_model = OpenAIModel(
    model_name=config.llm.model,
    provider=OpenAIProvider(
        base_url="http://localhost:11434/v1",
    ),
)

computron_agent = Agent(
    model=ollama_model,
    instructions=ROOT_AGENT_PROMPT,
    tools=[
        Tool(run_file_system_agent, takes_ctx=True, name="file_system"),
        Tool(run_web_agent, takes_ctx=True, name="web"),
        datetime_tool,
        execute_python_program,
        execute_nodejs_program,
    ],
)

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