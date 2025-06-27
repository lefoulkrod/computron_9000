import logging
import re
from typing import List

import bs4
from ollama import AsyncClient

from config import load_config
from tools.web.get_webpage_raw import _get_webpage_raw
from tools.web.types import GetWebpageError, ReducedWebpage, LinkInfo

logger = logging.getLogger(__name__)
config = load_config()

def _estimate_token_count(s: str) -> int:
    """
    Estimate the number of tokens in a string using a simple rule of thumb (1 token ≈ 4 characters).

    Args:
        s (str): The input string.

    Returns:
        int: Estimated token count.
    """
    return len(s) // 4

def _reduce_webpage_context(html: str) -> ReducedWebpage:
    """
    Reduce webpage HTML to essential text and extract links for LLM context efficiency.

    Args:
        html (str): Raw HTML content.

    Returns:
        ReducedWebpageContext: Contains page_text (all visible text, no HTML) and links (list of href/text from <a> tags).
    """
    soup = bs4.BeautifulSoup(html, "html.parser")

    # Extract all <a> elements in order
    links: List[LinkInfo] = []
    for a in soup.find_all("a"):
        if isinstance(a, bs4.element.Tag):
            href = str(a.get("href", "")) if a.has_attr("href") else ""
            text = a.get_text(strip=True)
            links.append(LinkInfo(href=href, text=text))

    # Remove all script/style/noscript/head/meta/link/base/iframe/svg/canvas tags
    for tag in soup([
        "script", "style", "noscript", "iframe", "svg", "canvas", "head", "meta", "link", "base"
    ]):
        tag.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, bs4.Comment)):
        comment.extract()

    # Get all visible text (strip all HTML tags)
    page_text = soup.get_text(separator=" ", strip=True)

    return ReducedWebpage(page_text=page_text, links=links)

async def _summarize_text(text: str) -> str:
    """
    Summarize the text by chunking it and calling the LLM to generate a concise summary for each chunk. Then combine the chunks into a single summary.

    Args:
        text (str): The text to summarize.

    Returns:
        str: The summarized text.
    """
    MODEL = config.llm.model
    chunk_size = 10000  # Adjust based on LLM capabilities
    overlap = 1000
    chunks = []
    i = 0
    while i < len(text):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
        if i + chunk_size >= len(text):
            break
        i += chunk_size - overlap
    logger.debug(f"Chunked text length {len(text)} into {len(chunks)} parts for summarization.")
    logger.debug(f"Estimated token count for input text: {_estimate_token_count(text)}")

    try:
        summaries = []
        for chunk in chunks:
            response = await AsyncClient().generate(
                model=MODEL, 
                prompt=f"summarize this text {chunk} /no_think",
                think=False
            )
            logger.debug(f"Chunk summary response: {response.response}")
            summaries.append(response.response)
        if len(summaries) > 1:
            combined_summary = " ".join(summaries)
            logger.debug(f"Estimated token count for combined summary: {_estimate_token_count(combined_summary)}")
            final_response = await AsyncClient().generate(
                model=MODEL,
                prompt=f"""
                This text is a set of summaries created by summarizing a longer text in chunks of {chunk_size}.
                Create a single summary from them. /no_think
                {combined_summary}""",
                think=False
            )
            logger.debug(f"Final summary response: {final_response.response}")
            return final_response.response
        return " ".join(summaries)
    except Exception as e:
        logger.error(f"Error summarizing text: {e}")
        return text

async def get_webpage(url: str) -> ReducedWebpage:
    """
    Downloads the web page at the given URL, strips all HTML tags, and returns the cleaned text content along with any links found on the page in the order they appear.

    Args:
        url (str): The URL of the web page to fetch. Must be a valid HTTP or HTTPS URL.

    Returns:
        ReducedWebpageContext: An object containing the reduced, cleaned text content of the page and the links found.

    Raises:
        GetWebpageError: For client or unknown errors.
    """
    raw_result = await _get_webpage_raw(url)
    html = raw_result.html
    try:
        if html:
            reduced = _reduce_webpage_context(html)
        else:
            reduced = ReducedWebpage(page_text="", links=[])
    except Exception as e:
        logger.error(f"Error reducing webpage content for {url}: {e}")
        raise GetWebpageError(f"Error reducing webpage content: {e}")
    return reduced


async def get_webpage_summary(url: str) -> str:
    """
    Downloads the web page at the given URL and summarizes its content.

    This function fetches the web page, extracts and cleans the visible text, and generates a brief summary suitable for LLM consumption. It is intended as a tool for language models to quickly understand the gist of a web page without processing the full content.

    Args:
        url (str): The URL of the web page to summarize. Must be a valid HTTP or HTTPS URL.

    Returns:
        str: A concise summary of the main content of the web page.

    Raises:
        GetWebpageError: If the page cannot be fetched or processed.
    """
    try:
        reduced = await get_webpage(url)
        return await _summarize_text(reduced.page_text)
    except Exception as e:
        logger.error(f"Error summarizing webpage for {url}: {e}")
        raise GetWebpageError(f"Error summarizing webpage: {e}")
