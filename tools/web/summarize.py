import logging
from typing import List

from config import load_config
from utils import generate_summary_with_ollama
import pydantic

logger = logging.getLogger(__name__)
config = load_config()

class ChunkSummary(pydantic.BaseModel):
    """
    Represents a summary of a larger block of text that has been chunked for summarization.

    Attributes:
        summary (str): The summary of the chunk.
        starting_char_position (int): The starting character position of the chunk in the original text.
        ending_char_position (int): The ending character position of the chunk in the original text.
    """
    summary: str
    starting_char_position: int
    ending_char_position: int

async def _summarize_text_full(text: str) -> str:
    """
    Summarize the text by first chunking it and summarizing each chunk, then combining those summaries into a final summary.

    Args:
        text (str): The text to summarize.

    Returns:
        str: The summarized text.
    """
    FINAL_PROMPT_TEMPLATE = (
        """
        This text is a set of summaries created by summarizing a longer text in chunks.\nCreate a single summary from them. /no_think\n{combined_summary}"""
    )
    try:
        chunk_summaries = await summarize_text_chunks(text)
        summaries = [chunk.summary for chunk in chunk_summaries]
        if len(summaries) > 1:
            combined_summary = " ".join(summaries)
            final_prompt = FINAL_PROMPT_TEMPLATE.format(combined_summary=combined_summary)
            final_response = await generate_summary_with_ollama(
                prompt=final_prompt,
                think=False
            )
            logger.debug(f"Final summary response: {final_response}")
            return final_response
        return " ".join(summaries)
    except Exception as e:
        logger.error(f"Error summarizing text: {e}")
        return text

async def summarize_text_chunks(text: str) -> List[ChunkSummary]:
    """
    Summarize the text by chunking it and calling the LLM to generate a concise summary for each chunk. Returns a list of chunk summaries with metadata.

    Args:
        text (str): The text to summarize.

    Returns:
        List[ChunkSummary]: List of chunk summaries with indices and positions.
    """
    PART_PROMPT_TEMPLATE = (
        "The following text is part {part_num} of {total_parts} of a larger document. "
        "Summarize this part as if it is not the whole. /no_think\n{chunk}"
    )
    chunk_size = 40000  # Adjust based on LLM capabilities
    overlap = 4000
    chunks = []
    positions = []
    i = 0
    while i < len(text):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
        positions.append((i, min(i + chunk_size, len(text))))
        if i + chunk_size >= len(text):
            break
        i += chunk_size - overlap

    logger.debug(f"Chunked text length {len(text)} into {len(chunks)} parts for summarization.")
    try:
        summaries: List[ChunkSummary] = []
        total_parts = len(chunks)
        for idx, (chunk, (start, end)) in enumerate(zip(chunks, positions)):
            part_num = idx + 1
            prompt = PART_PROMPT_TEMPLATE.format(part_num=part_num, total_parts=total_parts, chunk=chunk)
            response = await generate_summary_with_ollama(
                prompt=prompt,
                think=False
            )
            logger.debug(f"Chunk summary response: {response}")
            summaries.append(ChunkSummary(
                summary=response,
                starting_char_position=start,
                ending_char_position=end
            ))
        return summaries
    except Exception as e:
        logger.error(f"Error summarizing text chunks: {e}")
        raise
