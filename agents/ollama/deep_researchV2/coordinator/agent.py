"""Coordinator agent for orchestrating research tasks."""

# Standard library imports
import json
import logging

# Third-party imports
from pydantic import BaseModel, Field, ValidationError

# Local imports
from agents.ollama.deep_researchV2.topic_research import topic_research_agent_tool
from agents.ollama.deep_researchV2.web_search import web_search_agent_tool
from agents.types import Agent
from config import load_config
from models import get_default_model

from .prompt import PROMPT


class Subtopic(BaseModel):
    """Represents a summarized research subtopic with links.

    Args:
        title (str): The subtopic title.
        summary (str): Brief summary of the subtopic.
        links (list[str]): List of relevant links for the subtopic.
    """

    title: str = Field(..., description="The subtopic title.")
    summary: str = Field(..., description="Brief summary of the subtopic.")
    links: list[str] = Field(..., description="List of relevant links for the subtopic.")


class SubtopicSearchResults(BaseModel):
    """Represents the overall research results with subtopics.

    Args:
        subtopics (list[SubtopicResult]): List of subtopic summaries and links.
    """

    subtopics: list[Subtopic] = Field(..., description="List of subtopic summaries and links.")


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


config = load_config()
logger = logging.getLogger(__name__)
model = get_default_model()


async def execute_research_tool(research_topic: str) -> str:
    """Execute a deep research on the provided research topic.

    Args:
        research_topic (str): The main topic being researched.

    Returns:
        str: Research results summary.

    Raises:
        None
    """
    logger.debug("Executing research for topic: %s", research_topic)
    topic_overview = await web_search_agent_tool(f"""
    Perform a search on the topic: {research_topic}.
    Use a broad variety of sources to gather as much information as possible.
    Group the results into related subtopics and create a very brief summary of each subtopic.
    Gather the links for each subtopic together into a list and return them with the subtopic.
    You MUST return your results in JSON format with the following structure:
    {{
        "subtopics": [
            {{
                "title": "Subtopic 1",
                "summary": "Brief summary of subtopic 1.",
                "links": ["link1", "link2"]
            }},
            {{
                "title": "Subtopic 2",
                "summary": "Brief summary of subtopic 2.",
                "links": ["link3", "link4"]
            }}
        ]
    }}
    """)

    logger.debug("Research plan received: %s", topic_overview)
    try:
        overview_dict = json.loads(topic_overview)
        results = SubtopicSearchResults(**overview_dict)
    except (json.JSONDecodeError, ValidationError):
        logger.exception("Failed to parse research results.")
        raise

    detailed_subtopics = []
    for subtopic in results.subtopics:
        try:
            logger.debug("Researching subtopic: %s", subtopic.title)
            detailed = await topic_research_agent_tool(
                f"""
                Research the subtopic: {subtopic.title}:{subtopic.summary}
                Use these links for more details: {", ".join(subtopic.links)}
                """
            )
            detailed_subtopics.append(
                {
                    "title": subtopic.title,
                    "summary": subtopic.summary,
                    "links": subtopic.links,
                    "details": detailed,
                }
            )
        except Exception:
            logger.exception("Failed to research subtopic: %s", subtopic.title)
            detailed_subtopics.append(
                {
                    "title": subtopic.title,
                    "summary": subtopic.summary,
                    "links": subtopic.links,
                    "details": "Error researching subtopic",  # Placeholder for error handling
                }
            )
    return json.dumps(detailed_subtopics)


coordinator = Agent(
    name="COORDINATOR_AGENT",
    description="Orchestrates deep research tasks by coordinating multiple agents.",
    instruction=PROMPT,
    model=model.model,
    options=model.options,
    tools=[execute_research_tool],
    think=model.think,
)
