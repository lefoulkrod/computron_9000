from typing import List
from pydantic import BaseModel

__all__ = [
    "GetWebpageResult",
    "GetWebpageError",
    "LinkInfo",
    "ReducedWebpage",
]

class GetWebpageResult(BaseModel):
    """
    Output model for the webpage content.

    Args:
        url (str): The URL that was fetched.
        html (str): The full HTML content of the page.
        response_code (int): The HTTP response code returned by the server.
    """
    url: str
    html: str
    response_code: int

class GetWebpageError(Exception):
    """
    Custom exception for get_webpage tool errors.
    """
    pass

class LinkInfo(BaseModel):
    """
    Represents a hyperlink found in a web page.

    Args:
        href (str): The URL of the link.
        text (str): The visible text of the link.
    """
    href: str
    text: str

class ReducedWebpage(BaseModel):
    """
    Reduced representation of a web page for LLM context.

    Args:
        page_text (str): The visible text content of the page, with all HTML tags removed.
        links (List[LinkInfo]): List of links (anchor tags) found in the page, in order.
    """
    page_text: str
    links: List[LinkInfo]
