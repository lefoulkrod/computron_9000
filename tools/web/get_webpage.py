import logging
import re

import bs4

from tools.web.get_webpage_raw import get_webpage_raw
from tools.web.types import GetWebpageResult, GetWebpageError

logger = logging.getLogger(__name__)

def _reduce_webpage_context(html: str) -> str:
    """
    Reduce webpage HTML to essential content for LLM context efficiency, preserving structure and links, but removing <html> and <head> tags.

    Args:
        html (str): Raw HTML content.

    Returns:
        str: Reduced, cleaned HTML with structure and links preserved, and <html>/<head> removed.
    """
    soup = bs4.BeautifulSoup(html, "html.parser")

    # Remove scripts, styles, comments, and non-content tags
    for tag in soup([
        "script", "style", "noscript", "iframe", "svg", "canvas", "head", "meta", "link", "base"
    ]):
        tag.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, bs4.Comment)):
        comment.extract()

    # Remove unnecessary attributes, but preserve those needed for links and images
    allowed_attrs = {
        "a": ["href", "title", "name"],
        "img": ["src", "alt", "title"],
        "iframe": ["src", "title"],
        "form": ["action", "method"],
        "input": ["type", "name", "value", "placeholder"],
        "button": ["type", "name", "value"],
        "*": []  # For all other tags, remove all attributes
    }
    for tag in soup.find_all(True):
        if isinstance(tag, bs4.element.Tag):
            tag_name = tag.name.lower()
            attrs_to_keep = allowed_attrs.get(tag_name, allowed_attrs["*"])
            for attr in list(tag.attrs):
                if attr not in attrs_to_keep:
                    del tag.attrs[attr]

    # Optionally, remove empty tags (except <a> and <img>)
    for tag in soup.find_all(True):
        if isinstance(tag, bs4.element.Tag):
            if tag.name not in ["a", "img"] and not tag.contents and not tag.string:
                tag.decompose()

    # Remove <html> wrapper if present
    if soup.html:
        # Replace <html> with its children
        html_children = list(soup.html.children)
        new_html = "".join(str(child) for child in html_children if str(child).strip())
        return new_html
    return str(soup)


async def get_webpage(url: str) -> GetWebpageResult:
    """
    Fetch the main content from a web page for LLM consumption.

    This tool takes a URL, fetches the web page using get_webpage_raw, and returns the cleaned main content of the page. It removes scripts, styles, and extraneous HTML to provide only the essential readable text, making it suitable for LLMs or agents that need to process web content. Critical HTML elements, such as links, are retained in the output.

    Args:
        url (str): The URL of the web page to fetch. Must be a valid HTTP or HTTPS URL.

    Returns:
        GetWebpageResult: An object containing the original URL, the reduced, cleaned HTML/text content of the page, and the HTTP response code.

    Raises:
        GetWebpageError: For client or unknown errors.
    """
    raw_result = await get_webpage_raw(url)
    html = raw_result.html
    response_code = raw_result.response_code
    try:
        if html:
            reduced_html = _reduce_webpage_context(html)
        else:
            reduced_html = ""
    except Exception as e:
        logger.error(f"Error reducing webpage content for {url}: {e}")
        raise GetWebpageError(f"Error reducing webpage content: {e}")
    return GetWebpageResult(url=raw_result.url, html=reduced_html, response_code=response_code)
