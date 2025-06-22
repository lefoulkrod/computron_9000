import logging
from typing import List, Optional

from bs4 import BeautifulSoup
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class HtmlElementResult(BaseModel):
    """
    Pydantic model representing a found HTML element.

    Args:
        html_element (str): The HTML string of the matching element.
    """
    html_element: str

async def html_find_elements(
    html: str,
    tag: str,
    text: Optional[str] = None
) -> List[HtmlElementResult]:
    """
    Find elements of a given tag in HTML, optionally matching contained text.

    Args:
        html (str): The HTML string to parse.
        tag (str): The tag name to search for (e.g., 'a', 'div').
        text (Optional[str]): Optional text to match against the element's contained text.

    Returns:
        List[HtmlElementResult]: List of matching elements as HTML strings.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        if text is not None:
            matches = soup.find_all(tag, string=lambda t: isinstance(t, str) and text.lower() in t.lower())
        else:
            matches = soup.find_all(tag)
        return [HtmlElementResult(html_element=str(el)) for el in matches]
    except Exception as e:
        logger.error(f"Error in html_find_elements: {e}")
        return []
