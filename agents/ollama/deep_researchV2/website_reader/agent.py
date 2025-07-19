"""Agent for reading and analyzing website content for research subtopics.

This module provides an async tool to process a webpage, determine section relevance to a research
subtopic, and generate an overview using language model completions.
"""

from logging import getLogger
from typing import TYPE_CHECKING

from tools.web.get_webpage import get_webpage_substring, get_webpage_summary_sections

if TYPE_CHECKING:
    from tools.web.summarize import SectionSummary

from utils import generate_completion

logger = getLogger(__name__)


async def website_reader_agent_tool(url: str, research_subtopic: str) -> str:
    """Reads a webpage and generates a detailed overview based on the research subtopic.

    Args:
        url (str): The URL of the web page to process.
        research_subtopic (str): The research subtopic to focus on.

    Returns:
        str: The generated overview based on the webpage content and the research subtopic.
    """
    system_prompt = (
        f"You are conducting in-depth research on the topic: '{research_subtopic}'.\n"
        "You will be provided a summary of a section of a webpage. "
        "If the section is not relevant to the research subtopic, "
        "you MUST return the exact string 'skip'. If the section is relevant, "
        "you MUST return the exact string 'include'."
    )
    sections = await get_webpage_summary_sections(url)
    filtered_sections: list[SectionSummary] = []
    for section in sections:
        try:
            result = await generate_completion(
                prompt=f"Section summary: {section.summary}\n",
                system=system_prompt,
            )
        except Exception:
            logger.exception("Error during relevance check for section")
            continue
        if "skip" in result:
            logger.debug("Skipping section: %s", section.summary)
            continue
        if "include" in result:
            logger.debug("Including section: %s", section.summary)
            filtered_sections.append(section)

    detailed_results: list[str] = []
    for section in filtered_sections:
        try:
            # Get the substring of the section using its start and index
            substring = await get_webpage_substring(
                url=url,
                start=section.starting_char_position,
                end=section.ending_char_position,
            )
            detail = await generate_completion(
                prompt=(
                    f"Write a detailed overview of this section for the research subtopic "
                    f"'{research_subtopic}':\n{substring}"
                ),
                system=(
                    f"You are an expert researcher. You will be given a section of text from "
                    f"a webpage. Analyze the text based on the research "
                    f"topic:'{research_subtopic}'. Provide a detailed and comprehensive summary. "
                    f"Include code samples when applicable."
                ),
            )
            detailed_results.append(detail)
        except Exception:
            logger.exception("Error during detailed overview generation")
            continue

    return "\n".join(detailed_results)
