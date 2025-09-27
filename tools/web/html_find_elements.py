"""Utilities to find HTML elements using CSS selectors and BeautifulSoup."""

import logging

from bs4 import BeautifulSoup
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class HtmlElementResult(BaseModel):
    """Pydantic model representing a found HTML element.

    Args:
        html_element (str): The HTML string of the matching element.

    """

    html_element: str


async def html_find_elements(
    html: str,
    selectors: str | list[str],
    text: str | None = None,
) -> list[HtmlElementResult]:
    """Find elements in HTML matching given CSS selector(s), optionally filtering by contained text.

    Args:
        html (str): The HTML string to parse.
        selectors (Union[str, List[str]]): CSS selector(s) to search for. Examples:
            'a', 'div', '.classname', or ['a', '.foo'].
        text (Optional[str]): Optional text to match against the element's contained
            text.

    Returns:
        List[HtmlElementResult]: List of matching elements as HTML strings.

    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        all_matches = []

        # Ensure selectors is always a list for consistent processing
        selector_list = [selectors] if isinstance(selectors, str) else selectors

        for selector in selector_list:
            if text is not None:
                # For complex selectors, find elements then filter by text
                elements = soup.select(selector)
                text_matches = [
                    el
                    for el in elements
                    if el.string and isinstance(el.string, str) and text.lower() in el.string.lower()
                ]
                all_matches.extend(text_matches)
            else:
                matches = soup.select(selector)
                all_matches.extend(matches)

        return [HtmlElementResult(html_element=str(el)) for el in all_matches]
    except Exception:
        logger.exception("Error in html_find_elements")
        return []
