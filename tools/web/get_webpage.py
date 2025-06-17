import logging
import re

import bs4
from pydantic import BaseModel, HttpUrl, ValidationError, TypeAdapter

from playwright.async_api import async_playwright, Error as PlaywrightError

from config import load_config


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
        logging.error(f"Invalid URL: {url} | {e}")
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
    Navigate to a webpage and return its HTML content using Playwright.
    Applies post-processing to reduce context for LLMs.

    Args:
        url (str): The URL to get.

    Returns:
        GetWebpageResult: The result containing the URL and reduced content.

    Raises:
        GetWebpageError: If navigation or fetching fails.
    """
    validated_url = _validate_url(url)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(str(validated_url), timeout=15000)
            html = await page.content()
            await browser.close()
            html = _reduce_webpage_context(html)
            return GetWebpageResult(url=validated_url, html=html)
    except PlaywrightError as e:
        logging.error(f"Playwright error for {url}: {e}")
        raise GetWebpageError(f"Playwright error: {e}")
    except Exception as e:
        logging.error(f"Unexpected error for {url}: {e}")
        raise GetWebpageError(f"Unexpected error: {e}")
