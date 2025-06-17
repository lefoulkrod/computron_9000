import logging
import random
import time
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_sync

class GoogleSearchInput(BaseModel):
    """
    Input model for Google search.

    Args:
        query (str): The search query string.
        max_results (int): Maximum number of results to return (default: 5).
    """
    query: str = Field(..., min_length=1)
    max_results: int = 5

class GoogleSearchResult(BaseModel):
    """
    Output model for a single Google search result.

    Args:
        title (str): The result title.
        link (str): The result URL.
    """
    title: str
    link: str

class GoogleSearchResults(BaseModel):
    """
    Output model for all Google search results.

    Args:
        results (List[GoogleSearchResult]): List of search results.
    """
    results: List[GoogleSearchResult]

class GoogleSearchError(Exception):
    """
    Custom exception for Google search tool errors.
    """
    pass

def _human_delay(a: int, b: int) -> None:
    """
    Sleep for a random time between a and b milliseconds.
    """
    time.sleep(random.uniform(a / 1000, b / 1000))

def search_google(query: str, max_results: int = 5) -> GoogleSearchResults:
    """
    Search Google and return the top results using Playwright with stealth.

    Args:
        query (str): The search query string.
        max_results (int): Maximum number of results to return.

    Returns:
        GoogleSearchResults: The search results.

    Raises:
        GoogleSearchError: If search or scraping fails.
    """
    try:
        validated = GoogleSearchInput(query=query, max_results=max_results)
    except ValidationError as e:
        logging.error(f"Invalid input: {e}")
        raise GoogleSearchError(f"Invalid input: {e}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = ctx.new_page()
            stealth_sync(page)
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font", "media", "stylesheet"] else r.continue_())
            page.goto("https://www.google.com", timeout=15000)
            _human_delay(500, 1500)
            page.fill("input[name=q]", validated.query)
            _human_delay(200, 600)
            page.keyboard.press("Enter")
            _human_delay(2000, 4000)
            results = []
            for res in page.query_selector_all("div.g")[:validated.max_results]:
                title_el = res.query_selector("h3")
                link_el = res.query_selector("a")
                if title_el and link_el:
                    title = title_el.inner_text()
                    link = link_el.get_attribute("href")
                    if title and link:
                        results.append(GoogleSearchResult(title=title, link=link))
            browser.close()
            return GoogleSearchResults(results=results)
    except PlaywrightTimeoutError as e:
        logging.error(f"Timeout during Google search: {e}")
        raise GoogleSearchError(f"Timeout during Google search: {e}")
    except Exception as e:
        logging.error(f"Unexpected error during Google search: {e}")
        raise GoogleSearchError(f"Unexpected error during Google search: {e}")
