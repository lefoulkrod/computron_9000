import logging

from pydantic import BaseModel, HttpUrl, ValidationError, TypeAdapter

from playwright.async_api import async_playwright, Error as PlaywrightError


class OpenWebpageInput(BaseModel):
    """
    Input model for opening a webpage and fetching its contents.

    Args:
        url (HttpUrl): The URL of the webpage to fetch.
    """
    url: HttpUrl


class OpenWebpageResult(BaseModel):
    """
    Output model for the webpage content.

    Args:
        url (HttpUrl): The URL that was fetched.
        html (str): The full HTML content of the page.
    """
    url: HttpUrl
    html: str


class OpenWebpageError(Exception):
    """
    Custom exception for open_webpage tool errors.
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
        OpenWebpageError: If validation fails.
    """
    try:
        return TypeAdapter(HttpUrl).validate_python(url)
    except ValidationError as e:
        logging.error(f"Invalid URL: {url} | {e}")
        raise OpenWebpageError(f"Invalid URL: {e}")


async def open_webpage(url: str) -> OpenWebpageResult:
    """
    Navigate to a webpage and return its HTML content using Playwright.

    Args:
        url (str): The URL to open.

    Returns:
        OpenWebpageResult: The result containing the URL and HTML content.

    Raises:
        OpenWebpageError: If navigation or fetching fails.
    """
    validated_url = _validate_url(url)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(str(validated_url), timeout=15000)
            html = await page.content()
            await browser.close()
            return OpenWebpageResult(url=validated_url, html=html)
    except PlaywrightError as e:
        logging.error(f"Playwright error for {url}: {e}")
        raise OpenWebpageError(f"Playwright error: {e}")
    except Exception as e:
        logging.error(f"Unexpected error for {url}: {e}")
        raise OpenWebpageError(f"Unexpected error: {e}")
