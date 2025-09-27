"""Typed models used by the web utilities package.

Defines Pydantic models and exception types used by web scraping and
summarization helpers.
"""

from pydantic import BaseModel

__all__ = [
    "GetWebpageError",
    "GetWebpageResult",
    "LinkInfo",
    "ReducedWebpage",
]


class GetWebpageResult(BaseModel):
    """Output model for the webpage content.

    A model representing the result of a web page fetch operation.

    Attributes:
        url (str): The URL that was fetched.
        html (str): The full HTML content of the page.
        response_code (int): The HTTP response code returned by the server.

    """

    url: str
    html: str
    response_code: int


class GetWebpageError(Exception):
    """Custom exception for get_webpage tool errors.

    Used when web page fetching operations fail.
    """


class LinkInfo(BaseModel):
    """Represents a hyperlink found in a web page.

    Contains the URL and visible text of a hyperlink.

    Attributes:
        href (str): The URL of the link.
        text (str): The visible text of the link.

    """

    href: str
    text: str


class ReducedWebpage(BaseModel):
    """Reduced representation of a web page for LLM context.

    Provides a simplified version of a web page with extracted text and links,
    suitable for passing to language models with limited context windows.

    Attributes:
        page_text (str): The visible text content of the page, with all HTML tags removed.
        links (List[LinkInfo]): List of links (anchor tags) found in the page, in order.

    """

    page_text: str
    links: list[LinkInfo]
