import logging

import aiohttp
from pydantic import HttpUrl, TypeAdapter, ValidationError

from tools.web.types import GetWebpageError, GetWebpageResult

logger = logging.getLogger(__name__)


def _validate_url(url: str) -> str:
    """
    Validate a string URL and return it if valid.

    Args:
        url (str): The URL to validate.

    Returns:
        str: The validated URL as a string.

    Raises:
        GetWebpageError: If validation fails.
    """
    try:
        TypeAdapter(HttpUrl).validate_python(url)
        return url
    except ValidationError as e:
        logger.error(f"Invalid URL: {url} | {e}")
        raise GetWebpageError(f"Invalid URL: {e}") from e


async def _get_webpage_raw(url: str) -> GetWebpageResult:
    """
    Fetch the raw HTML content from a web page, simulating a real browser to avoid being blocked.

    Args:
        url (str): The URL of the web page to fetch. Must be a valid HTTP or HTTPS URL.

    Returns:
        GetWebpageResult: An object containing the original URL, the raw HTML content of the page, and the HTTP response code.

    Raises:
        GetWebpageError: For client or unknown errors.
    """
    validated_url = _validate_url(url)
    html = ""
    response_code = None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with (
            aiohttp.ClientSession(timeout=timeout, headers=headers) as session,
            session.get(validated_url) as response,
        ):
            response_code = response.status
            try:
                html = await response.text()
            except Exception as e:
                logger.error(f"Failed to read response body for {url}: {e}")
                html = ""
            if response_code != 200:
                logger.debug(f"Non-200 response for {url}: HTTP {response_code}")
        return GetWebpageResult(
            url=validated_url, html=html, response_code=response_code
        )
    except aiohttp.ClientError as e:
        logger.error(f"aiohttp error for {url}: {e}")
        raise GetWebpageError(f"aiohttp error: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error for {url}: {e}")
        raise GetWebpageError(f"Unexpected error: {e}") from e
