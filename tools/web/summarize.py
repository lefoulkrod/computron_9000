import logging

import pydantic

from config import load_config
from utils import generate_summary_with_ollama

logger = logging.getLogger(__name__)
config = load_config()


class SectionSummary(pydantic.BaseModel):
    """Represents a summary of a section of a larger block of text that has been divided for summarization.

    Attributes:
        summary (str): The summary of the section.
        starting_char_position (int): The starting character position of the section in the original text.
        ending_char_position (int): The ending character position of the section in the original text.

    """

    summary: str
    starting_char_position: int
    ending_char_position: int


async def _summarize_text_full(text: str) -> str:
    """Summarize the text by first dividing it into sections and summarizing each section, then combining those summaries into a final summary.

    Args:
        text (str): The text to summarize.

    Returns:
        str: The summarized text.

    """
    final_prompt_template = """
        This text is a set of summaries created by summarizing a longer text in sections.\nCreate a single summary from them. /no_think\n{combined_summary}"""
    try:
        section_summaries = await summarize_text_sections(text)
        summaries = [section.summary for section in section_summaries]
        if len(summaries) > 1:
            combined_summary = " ".join(summaries)
            final_prompt = final_prompt_template.format(
                combined_summary=combined_summary,
            )
            final_response = await generate_summary_with_ollama(
                prompt=final_prompt,
                think=False,
            )
            logger.debug(f"Final summary response: {final_response}")
            return final_response
        return " ".join(summaries)
    except Exception as e:
        logger.error(f"Error summarizing text: {e}")
        return text


async def summarize_text_sections(text: str) -> list[SectionSummary]:
    """Summarize the text by dividing it into sections and calling the LLM to generate a concise summary for each section. Returns a list of section summaries with metadata.

    Args:
        text (str): The text to summarize.

    Returns:
        List[SectionSummary]: List of section summaries with indices and positions.

    """
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
        f"Divided text length {len(text)} into {len(sections)} parts for summarization.",
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
            response = await generate_summary_with_ollama(prompt=prompt, think=False)
            logger.debug(f"Section summary response: {response}")
            summaries.append(
                SectionSummary(
                    summary=response,
                    starting_char_position=start,
                    ending_char_position=end,
                ),
            )
        return summaries
    except Exception as e:
        logger.error(f"Error summarizing text sections: {e}")
        raise
