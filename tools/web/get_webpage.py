import logging
import re

import aiohttp
import bs4
from pydantic import BaseModel, HttpUrl, ValidationError, TypeAdapter

from config import load_config


logger = logging.getLogger(__name__)


class GetWebpageInput(BaseModel):
    """
    Input model for getting a webpage and fetching its contents.

    Args:
        url (HttpUrl): The URL of the webpage to fetch.
    """
    url: HttpUrl


class GetWebpageResult(BaseModel):
    """
    Output model for the webpage content.

    Args:
        url (HttpUrl): The URL that was fetched.
        html (str): The full HTML content of the page.
    """
    url: HttpUrl
    html: str


class GetWebpageError(Exception):
    """
    Custom exception for get_webpage tool errors.
    """
    pass


def _validate_url(url: str) -> HttpUrl:
    """
    Validate and convert a string URL to HttpUrl.

    Args:
        url (str): The URL to validate.

    Returns:
        HttpUrl: The validated URL.

    Raises:
        GetWebpageError: If validation fails.
    """
    try:
        return TypeAdapter(HttpUrl).validate_python(url)
    except ValidationError as e:
        logger.error(f"Invalid URL: {url} | {e}")
        raise GetWebpageError(f"Invalid URL: {e}")


def _reduce_webpage_context(html: str) -> str:
    """
    Reduce webpage HTML to essential content for LLM context efficiency.

    Args:
        html (str): Raw HTML content.

    Returns:
        str: Reduced, cleaned HTML/text.
    """
    soup = bs4.BeautifulSoup(html, "html.parser")

    # Remove scripts, styles, comments, and non-content tags
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "canvas", "head", "meta", "link", "base"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, bs4.Comment)):
        comment.extract()

    # Remove unnecessary attributes
    for tag in soup.find_all(True):
        if isinstance(tag, bs4.element.Tag):
            for attr in list(tag.attrs):
                if attr in ["style", "class", "id", "on"]:
                    del tag.attrs[attr]

    # Optionally flatten layout tags
    for tag in soup.find_all(["div", "span"]):
        if isinstance(tag, bs4.element.Tag):
            tag.unwrap()

    # Extract main content
    main_content = None
    for main_tag in ["main", "article", "section"]:
        main_content = soup.find(main_tag)
        if main_content:
            break
    if not main_content:
        main_content = soup.body or soup

    # Collapse whitespace
    text = main_content.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    return text


async def get_webpage(url: str) -> GetWebpageResult:
    """
    Fetch the main content from a web page for LLM consumption.

    This tool takes a URL, fetches the web page using a simple HTTP GET request, and returns the cleaned main content of the page. It removes scripts, styles, and extraneous HTML to provide only the essential readable text, making it suitable for LLMs or agents that need to process web content. Critical HTML elements, such as links, are retained in the output.

    Args:
        url (str): The URL of the web page to fetch. Must be a valid HTTP or HTTPS URL.

    Returns:
        GetWebpageResult: An object containing the original URL and the reduced, cleaned HTML/text content of the page.

    Raises:
        GetWebpageError: If the URL is invalid or the page cannot be fetched.
    """
    validated_url = _validate_url(url)
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(str(validated_url)) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch {url}: HTTP {response.status}")
                    raise GetWebpageError(f"HTTP error: {response.status}")
                html = await response.text()
        html = _reduce_webpage_context(html)
        return GetWebpageResult(url=validated_url, html=html)
    except aiohttp.ClientError as e:
        logger.error(f"aiohttp error for {url}: {e}")
        raise GetWebpageError(f"aiohttp error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error for {url}: {e}")
        raise GetWebpageError(f"Unexpected error: {e}")
