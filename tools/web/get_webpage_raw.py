import logging

import aiohttp
from pydantic import HttpUrl, ValidationError, TypeAdapter

from tools.web.schemas import GetWebpageResult, GetWebpageError

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
        raise GetWebpageError(f"Invalid URL: {e}")

async def get_webpage_raw(url: str) -> GetWebpageResult:
    """
    Fetch the raw HTML content from a web page.

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
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(validated_url) as response:
                response_code = response.status
                try:
                    html = await response.text()
                except Exception as e:
                    logger.error(f"Failed to read response body for {url}: {e}")
                    html = ""
                if response_code != 200:
                    logger.debug(f"Non-200 response for {url}: HTTP {response_code}")
        return GetWebpageResult(url=validated_url, html=html, response_code=response_code)
    except aiohttp.ClientError as e:
        logger.error(f"aiohttp error for {url}: {e}")
        raise GetWebpageError(f"aiohttp error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error for {url}: {e}")
        raise GetWebpageError(f"Unexpected error: {e}")
