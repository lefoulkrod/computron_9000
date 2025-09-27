"""Higher-level webpage utilities for extraction and summarization.

This module provides functions that reduce webpage HTML to plain text and
generate summaries suitable for LLM consumption.
"""

import logging

import bs4

from config import load_config
from tools.web.get_webpage_raw import _get_webpage_raw
from tools.web.summarize import (
    SectionSummary,
    _summarize_text_full,
    summarize_text_sections,
)
from tools.web.types import GetWebpageError, LinkInfo, ReducedWebpage
from utils.cache import async_lru_cache

logger = logging.getLogger(__name__)
config = load_config()


def _reduce_webpage_context(html: str) -> ReducedWebpage:
    """Reduce webpage HTML to essential text and extract links for LLM context efficiency.

    Args:
        html (str): Raw HTML content.

    Returns:
        ReducedWebpage: Contains page_text (all visible text, no HTML) and links (list of
            href/text from <a> tags).
    """
    soup: bs4.BeautifulSoup = bs4.BeautifulSoup(html, "html.parser")

    links: list[LinkInfo] = []
    for a in soup.find_all("a"):
        if isinstance(a, bs4.element.Tag):
            href: str = str(a.get("href", "")) if a.has_attr("href") else ""
            text: str = a.get_text(strip=True)
            links.append(LinkInfo(href=href, text=text))

    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "iframe",
            "svg",
            "canvas",
            "head",
            "meta",
            "link",
            "base",
        ]
    ):
        tag.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, bs4.Comment)):
        comment.extract()

    page_text: str = soup.get_text(separator=" ", strip=True)
    return ReducedWebpage(page_text=page_text, links=links)


@async_lru_cache(maxsize=10)
async def get_webpage(url: str) -> ReducedWebpage:
    """Downloads the web page at the given URL, strips all HTML tags, and returns the cleaned.

    text content along with any links found on the page in the order they appear.

    Args:
        url (str): The URL of the web page to fetch. Must be a valid HTTP or HTTPS URL.

    Returns:
        ReducedWebpage: An object containing the reduced, cleaned text content of the page and
            the links found.

    Raises:
        GetWebpageError: For client or unknown errors.
    """
    raw_result = await _get_webpage_raw(url)
    html: str = raw_result.html
    try:
        reduced: ReducedWebpage = _reduce_webpage_context(html) if html else ReducedWebpage(page_text="", links=[])
    except (ValueError, RuntimeError) as exc:
        logger.exception("Error reducing webpage content for %s", url)
        raise GetWebpageError(exc) from exc
    return reduced


async def get_webpage_summary(url: str) -> str:
    """Downloads the web page at the given URL and summarizes its content.

    This function fetches the web page, extracts and cleans the visible text, and generates a
    brief summary suitable for LLM consumption. It is intended as a tool for language models to
    quickly understand the gist of a web page without processing the full content.

    Args:
        url (str): The URL of the web page to summarize. Must be a valid HTTP or HTTPS URL.

    Returns:
        str: A concise summary of the main content of the web page.

    Raises:
        GetWebpageError: If the page cannot be fetched or processed.
    """
    try:
        reduced: ReducedWebpage = await get_webpage(url)
        return await _summarize_text_full(reduced.page_text)
    except (GetWebpageError, ValueError, RuntimeError) as exc:
        logger.exception("Error summarizing webpage for %s", url)
        msg = f"Error summarizing webpage: {exc}"
        raise GetWebpageError(msg) from exc


async def get_webpage_substring(url: str, start: int, end: int) -> str:
    """Fetches a web page, extracts the visible text, and returns a substring.

    This tool can be used to get a specific portion of the text from a web page.
    It will return the substring from the specified start index to the end index (exclusive).

    Args:
        url (str): The URL of the web page to fetch.
        start (int): The starting index of the substring.
        end (int): The ending index of the substring (exclusive).

    Returns:
        str: The substring of the web page's visible text.

    Raises:
        GetWebpageError: If the page cannot be fetched or processed.
        ValueError: If indices are invalid.
    """
    try:
        reduced: ReducedWebpage = await get_webpage(url)
    except BaseException as exc:  # Intentionally broad: wrap any error from get_webpage -> GetWebpageError
        logger.exception("Error fetching webpage for substring: %s", url)
        msg = f"Error fetching webpage: {exc}"
        raise GetWebpageError(msg) from exc
    page_text: str = reduced.page_text
    if not (0 <= start <= end <= len(page_text)):
        logger.error(
            "Invalid substring indices: start=%d, end=%d, text length=%d",
            start,
            end,
            len(page_text),
        )
        msg = f"Invalid substring indices: start={start}, end={end}, text length={len(page_text)}"
        raise ValueError(msg)
    try:
        return page_text[start:end]
    except (IndexError, ValueError) as exc:
        logger.exception("Error getting webpage substring for %s", url)
        msg = f"Error getting webpage substring: {exc}"
        raise GetWebpageError(msg) from exc


async def get_webpage_summary_sections(url: str) -> list[SectionSummary]:
    """Downloads the web page at the given URL and summarizes its content in sections.

    This function fetches the web page, extracts and cleans the visible text, and summarizes it
    in overlapping sections. It generates a summary for each section and returns them as a list.
    Each summary includes the section text and its starting and ending character positions in the
    original text.

    Args:
        url (str): The URL of the web page to summarize. Must be a valid HTTP or HTTPS URL.

    Returns:
        list[SectionSummary]: List of section summaries.

    Raises:
        GetWebpageError: If the page cannot be fetched or processed.
    """
    try:
        reduced: ReducedWebpage = await get_webpage(url)
        return await summarize_text_sections(reduced.page_text)
    except (GetWebpageError, ValueError, RuntimeError) as exc:
        logger.exception("Error summarizing webpage in sections for %s", url)
        raise GetWebpageError(str(exc)) from exc
