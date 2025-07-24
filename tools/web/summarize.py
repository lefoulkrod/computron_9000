"""Text summarization utilities for web tools.

Provides async functions for sectioned and full-text summarization using LLMs.
"""

import logging

import pydantic

from config import load_config
from models import generate_completion, get_default_model

logger = logging.getLogger(__name__)
config = load_config()


class SectionSummary(pydantic.BaseModel):
    """Summary of a section of a larger block of text.

    Attributes:
        summary: The summary of the section.
        starting_char_position: The starting character position of the section in the original text.
        ending_char_position: The ending character position of the section in the original text.
    """

    summary: str
    starting_char_position: int
    ending_char_position: int


async def _summarize_text_full(text: str) -> str:
    """Summarize the text by dividing it into sections, summarizing each, and combining into a final summary.

    Args:
        text: The text to summarize.

    Returns:
        The summarized text.

    """
    model = get_default_model()
    final_prompt_template = (
        "This text is a set of summaries created by summarizing a longer text in sections.\n"
        "Create a single summary from them. /no_think\n{combined_summary}"
    )
    try:
        section_summaries = await summarize_text_sections(text)
        summaries = [section.summary for section in section_summaries]
        if len(summaries) > 1:
            combined_summary = " ".join(summaries)
            final_prompt = final_prompt_template.format(combined_summary=combined_summary)
            final_response, _ = await generate_completion(
                prompt=final_prompt,
                model=model.model,
                think=False,
                system="You are an expert summarizer. Create a concise summary from the provided section summaries.",
                options=model.options,
            )
            logger.debug("Final summary response: %s", final_response)
            return final_response
        return " ".join(summaries)
    except Exception:
        logger.exception("Error summarizing text")
        return text


async def summarize_text_sections(text: str) -> list[SectionSummary]:
    """Summarize the text by dividing it into sections and calling the LLM to generate a concise summary for each section.

    Args:
        text: The text to summarize.

    Returns:
        List of section summaries with indices and positions.

    """
    model = get_default_model()
    part_prompt_template = (
        "The following text is part {part_num} of {total_parts} of a larger document. "
        "Summarize this part as if it is not the whole. /no_think\n{section}"
    )
    section_size = 40000  # Adjust based on LLM capabilities
    overlap = 4000
    sections = []
    positions = []
    i = 0
    while i < len(text):
        section = text[i : i + section_size]
        sections.append(section)
        positions.append((i, min(i + section_size, len(text))))
        if i + section_size >= len(text):
            break
        i += section_size - overlap

    logger.debug(
        "Divided text length %d into %d parts for summarization.", len(text), len(sections)
    )
    try:
        summaries: list[SectionSummary] = []
        total_parts = len(sections)
        for idx, (section, (start, end)) in enumerate(
            zip(sections, positions, strict=False),
        ):
            part_num = idx + 1
            prompt = part_prompt_template.format(
                part_num=part_num,
                total_parts=total_parts,
                section=section,
            )
            response, _ = await generate_completion(
                prompt=prompt,
                model=model.model,
                think=False,
                system="You are an expert summarizer. Create a concise summary of the provided text section.",
                options=model.options,
            )
            logger.debug("Section summary response: %s", response)
            summaries.append(
                SectionSummary(
                    summary=response,
                    starting_char_position=start,
                    ending_char_position=end,
                ),
            )
    except Exception:
        logger.exception("Error summarizing text sections")
        raise
    else:
        return summaries
