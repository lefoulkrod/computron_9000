"""Web agent using Pydantic AI API (decorator-based tools, async)."""

import logging
from typing import Any

from pydantic_ai import Agent, RunContext
from config import load_config
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from agents.prompt import WEB_AGENT_PROMPT
from tools.web import get_webpage_substring, get_webpage_summary_sections
from tools.web.search_google import search_google
from tools.code.execute_code import execute_nodejs_program_with_playwright

logger = logging.getLogger(__name__)

config = load_config()

ollama_model = OpenAIModel(
    model_name=config.llm.model,
    provider=OpenAIProvider(
        base_url="http://localhost:11434/v1",
    ),
)

web_agent = Agent(
    model=ollama_model,
    instructions=WEB_AGENT_PROMPT,
    tools=[
        get_webpage_summary_sections,
        get_webpage_substring,
        search_google,
    ],
)

async def run_web_agent(ctx: RunContext[None], instructions: str) -> Any:
    """
    Tool for delegating internet-enabled goal achievement to a specialized web agent.

    This function acts as a tool that allows other agents to hand off complex, internet-enabled tasks to a dedicated web agent. The web agent can perform web search, navigation, extraction, and multi-step workflows to achieve specified goals. Callers should provide detailed, step-by-step instructions describing the specific goal or outcome they want the web agent to accomplish. This enables seamless delegation of internet-based objectives within multi-agent systems, ensuring the web agent can follow a clear, actionable plan.

    Args:
        ctx (RunContext[None]): The agent run context, including usage tracking and metadata.
        instructions (str): Detailed instructions describing the goal the web agent should achieve using internet resources.

    Returns:
        Any: The agent's structured response to the web operation, or an error message if the operation fails.

    Raises:
        Logs and returns an error dictionary if an exception occurs during execution.
    """
    agent_input = instructions
    if not config.agents.web.think:
        agent_input = instructions + " /no_think"
    logger.debug(f"Running web agent with instructions: {agent_input}")
    try:
        result = await web_agent.run(agent_input, usage=ctx.usage)
        return result.output
    except Exception as exc:
        logger.error(f"Web agent error: {exc}", exc_info=True)
        return {"error": str(exc)}
