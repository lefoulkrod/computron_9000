"""Coordinator agent for orchestrating research tasks."""

import logging

from pydantic import BaseModel, Field

from agents.ollama.web_agent import web_agent_tool
from agents.types import Agent
from config import load_config
from models import get_default_model

from .prompt import PROMPT

config = load_config()
logger = logging.getLogger(__name__)
model = get_default_model()


class ResearchSubtopic(BaseModel):
    """Represents a specific subtopic within a research topic.

    Args:
        subtopic (str): A specific subtopic to research.
    """

    subtopic: str = Field(..., description="A specific subtopic to research.")


class ExecuteResearchInput(BaseModel):
    """Input model for executing research on a topic and its subtopics.

    Args:
        research_topic (str): The main topic being researched.
        subtopics (list[ResearchSubtopic]): A list of subtopics to research.
    """

    research_topic: str = Field(..., description="The main research topic being researched.")
    subtopics: list[ResearchSubtopic] = Field(..., description="A list of subtopics to research.")


async def get_topic_overview(research_topic: str) -> str:
    """Get an overview of the research topic.

    Given the original research topic, provide an overview of the topic
    using up-to-date information.

    Args:
        research_topic (str): The main research topic being researched.

    Returns:
        str: Overview of the topic.

    Raises:
        None
    """
    logger.debug("Getting topic overview for research_topic: %s", research_topic)
    web_agent_tool_instructions = f"""
    Use your available tools to get up to date information on the following research
    topic: {research_topic}. Provide a broad and comprehensive overview of the topic.
    The overview will be used to break down the research into subtopics which will each
    be investigated in detail.
    """
    overview = await web_agent_tool(web_agent_tool_instructions)
    logger.debug("Overview received: %s", overview)
    return overview


async def execute_research(input_data: ExecuteResearchInput) -> str:
    """Execute research on the provided subtopics.

    Args:
        input_data (ExecuteResearchInput):
            Strongly typed input with research topic and subtopics.

    Returns:
        str: Research results summary.

    Raises:
        None
    """
    logger.info("Executing research for topic: %s", input_data.research_topic)
    results = []
    for sub in input_data.subtopics:
        logger.debug("Researching subtopic: %s", sub.subtopic)
        results.append(f"Research on {sub.subtopic}")
    return f"Research for {input_data.research_topic}: " + ", ".join(results)


coordinator = Agent(
    name="COORDINATOR_AGENT",
    description="Orchestrates deep research tasks by coordinating multiple agents.",
    instruction=PROMPT,
    model=model.model,
    options=model.options,
    tools=[get_topic_overview, execute_research],
)
