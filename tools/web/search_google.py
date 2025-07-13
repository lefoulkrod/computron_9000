import asyncio
import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from pydantic import BaseModel, Field, ValidationError

from config import load_config

logger = logging.getLogger(__name__)


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
        snippet (str): The result snippet/description.
    """

    title: str
    link: str
    snippet: str = ""


class GoogleSearchResults(BaseModel):
    """
    Output model for all Google search results.

    Args:
        results (List[GoogleSearchResult]): List of search results.
    """

    results: list[GoogleSearchResult]


class GoogleSearchError(Exception):
    """
    Custom exception for Google search tool errors.
    """

    pass


class FingerprintConfig(BaseModel):
    """
    Browser fingerprint configuration.

    Args:
        device_name (str): Device name to use.
        locale (str): Browser locale.
        timezone_id (str): Timezone identifier.
        color_scheme (str): Color scheme preference.
        reduced_motion (str): Reduced motion preference.
        forced_colors (str): Forced colors preference.
    """

    device_name: str
    locale: str
    timezone_id: str
    color_scheme: str
    reduced_motion: str
    forced_colors: str


class SavedState(BaseModel):
    """
    Saved browser state configuration.

    Args:
        fingerprint (Optional[FingerprintConfig]): Browser fingerprint config.
        google_domain (Optional[str]): Preferred Google domain.
    """

    fingerprint: FingerprintConfig | None = None
    google_domain: str | None = None


def _get_host_machine_config(user_locale: str | None = None) -> FingerprintConfig:
    """
    Get host machine configuration for browser fingerprinting.

    Args:
        user_locale (Optional[str]): User specified locale.

    Returns:
        FingerprintConfig: Browser fingerprint configuration.
    """
    # Get system locale
    system_locale = user_locale or os.environ.get("LANG", "en-US")

    # Get system timezone - simplified approach
    current_time = datetime.now()
    timezone_offset = current_time.astimezone().utcoffset()

    # Map timezone based on offset (simplified)
    if timezone_offset:
        hours = timezone_offset.total_seconds() / 3600
        if -9 <= hours <= -8:
            timezone_id = "Asia/Shanghai"
        elif -10 <= hours <= -9:
            timezone_id = "Asia/Tokyo"
        elif -8 <= hours <= -7:
            timezone_id = "Asia/Bangkok"
        elif -1 <= hours <= 1:
            timezone_id = "Europe/London"
        elif -6 <= hours <= -4:
            timezone_id = "America/New_York"
        else:
            timezone_id = "UTC"
    else:
        timezone_id = "UTC"

    # Determine color scheme based on time
    hour = current_time.hour
    color_scheme = "dark" if hour >= 19 or hour < 7 else "light"

    # Other settings
    reduced_motion = "no-preference"
    forced_colors = "none"
    device_name = "Desktop Chrome"

    return FingerprintConfig(
        device_name=device_name,
        locale=system_locale,
        timezone_id=timezone_id,
        color_scheme=color_scheme,
        reduced_motion=reduced_motion,
        forced_colors=forced_colors,
    )


def _get_device_config(saved_state: SavedState) -> tuple[str, dict[str, Any]]:
    """
    Get device configuration for browser context.

    Args:
        saved_state (SavedState): Saved browser state.

    Returns:
        tuple[str, Dict[str, Any]]: Device name and configuration.
    """
    # Available desktop devices (simplified)
    desktop_devices = {
        "Desktop Chrome": {
            "viewport": {"width": 1280, "height": 720},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        },
        "Desktop Firefox": {
            "viewport": {"width": 1280, "height": 720},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        },
        "Desktop Safari": {
            "viewport": {"width": 1280, "height": 720},
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Version/16.5 Safari/537.36",
        },
    }

    device_list = list(desktop_devices.keys())

    if (
        saved_state.fingerprint
        and saved_state.fingerprint.device_name in desktop_devices
    ):
        device_name = saved_state.fingerprint.device_name
    else:
        device_name = random.choice(device_list)  # noqa: S311

    return device_name, desktop_devices[device_name]


BROWSER_LOCALE = "en-US"


async def search_google(query: str, max_results: int = 5) -> GoogleSearchResults:
    """
    Search Google and return the top results.

    Args:
        query (str): The search query string.
        max_results (int): Maximum number of results to return.

    Returns:
        GoogleSearchResults: The search results.

    Raises:
        GoogleSearchError: If search fails.
    """
    try:
        validated = GoogleSearchInput(query=query, max_results=max_results)
    except ValidationError as e:
        logger.error(f"Invalid input: {e}")
        raise GoogleSearchError(f"Invalid input: {e}") from e

    # Load configuration
    config = load_config()
    home_dir = config.settings.home_dir
    state_file = config.tools.web.search_google.state_file
    no_save_state = config.tools.web.search_google.no_save_state
    timeout = config.tools.web.search_google.timeout

    # Combine home_dir and state_file for the full state path
    state_path = Path(home_dir) / state_file
    fingerprint_file = state_path.with_name(state_path.stem + "-fingerprint.json")

    saved_state = SavedState()
    storage_state = None

    if state_path.exists():
        logger.debug(f"Found browser state file: {state_path}")
        storage_state = str(state_path)

        # Load fingerprint config if available
        if fingerprint_file.exists():
            try:
                with fingerprint_file.open(encoding="utf-8") as f:
                    fingerprint_data = json.load(f)
                    saved_state = SavedState(**fingerprint_data)
                logger.debug("Loaded saved browser fingerprint configuration")
            except Exception as e:
                logger.warning(f"Cannot load fingerprint config: {e}")
    else:
        logger.debug("No browser state file found, creating new session")

    # Google domain options
    google_domains = [
        "https://www.google.com",
        "https://www.google.co.uk",
        "https://www.google.ca",
        "https://www.google.com.au",
    ]

    # Patterns to detect captcha/verification pages
    sorry_patterns = [
        "google.com/sorry/index",
        "google.com/sorry",
        "recaptcha",
        "captcha",
        "unusual traffic",
    ]

    async def _perform_search(headless: bool = True) -> GoogleSearchResults:
        """
        Internal function to perform the search.

        Args:
            headless (bool): Whether to run in headless mode.

        Returns:
            GoogleSearchResults: Search results.
        """
        async with async_playwright() as p:
            # Launch browser with anti-detection arguments
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-site-isolation-trials",
                    "--disable-web-security",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--no-first-run",
                    "--no-zygote",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--mute-audio",
                    "--disable-background-networking",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-breakpad",
                    "--disable-component-extensions-with-background-pages",
                    "--disable-extensions",
                    "--disable-features=TranslateUI",
                    "--disable-ipc-flooding-protection",
                    "--disable-renderer-backgrounding",
                    "--enable-features=NetworkService,NetworkServiceInProcess",
                    "--force-color-profile=srgb",
                    "--metrics-recording-only",
                ],
            )

            try:
                # Get device configuration
                device_name, device_config = _get_device_config(saved_state)

                # Create context options
                context_options = {
                    **device_config,
                    "permissions": ["geolocation", "notifications"],
                    "accept_downloads": True,
                    "java_script_enabled": True,
                }

                # Apply fingerprint configuration
                if saved_state.fingerprint:
                    context_options.update(
                        {
                            "locale": BROWSER_LOCALE,
                            "timezone_id": saved_state.fingerprint.timezone_id,
                            "color_scheme": saved_state.fingerprint.color_scheme,
                            "reduced_motion": saved_state.fingerprint.reduced_motion,
                            "forced_colors": saved_state.fingerprint.forced_colors,
                        }
                    )
                    logger.debug("Using saved fingerprint configuration")
                else:
                    # Generate new fingerprint
                    host_config = _get_host_machine_config(BROWSER_LOCALE)
                    context_options.update(
                        {
                            "locale": BROWSER_LOCALE,
                            "timezone_id": host_config.timezone_id,
                            "color_scheme": host_config.color_scheme,
                            "reduced_motion": host_config.reduced_motion,
                            "forced_colors": host_config.forced_colors,
                        }
                    )
                    saved_state.fingerprint = host_config
                    logger.debug("Generated new fingerprint configuration")

                # Add storage state if available
                if storage_state:
                    context_options["storage_state"] = storage_state

                context = await browser.new_context(**context_options)

                page = await context.new_page()
                # Block unnecessary resources
                await page.route(
                    "**/*",
                    lambda route: (
                        asyncio.create_task(route.abort())
                        if route.request.resource_type
                        in ["image", "font", "media", "stylesheet"]
                        else asyncio.create_task(route.continue_())
                    ),
                )

                # Select Google domain
                if saved_state.google_domain:
                    selected_domain = saved_state.google_domain
                    logger.debug(f"Using saved Google domain: {selected_domain}")
                else:
                    selected_domain = random.choice(google_domains)  # noqa: S311
                    saved_state.google_domain = selected_domain
                    logger.debug(f"Selected Google domain: {selected_domain}")

                # Navigate to Google
                logger.debug("Navigating to Google search page...")
                response = await page.goto(
                    selected_domain, timeout=timeout, wait_until="networkidle"
                )

                # Check for captcha/verification page
                current_url = page.url
                is_blocked = any(pattern in current_url for pattern in sorry_patterns)
                if response:
                    is_blocked = is_blocked or any(
                        pattern in response.url for pattern in sorry_patterns
                    )

                if is_blocked and headless:
                    logger.warning(
                        "Detected verification page, retrying in headed mode..."
                    )
                    await page.close()
                    await context.close()
                    await browser.close()
                    return await _perform_search(headless=False)
                if is_blocked:
                    logger.warning(
                        "Verification page detected, waiting for manual completion..."
                    )
                    await page.wait_for_url(
                        lambda url: not any(
                            pattern in url for pattern in sorry_patterns
                        ),
                        timeout=timeout * 2,
                    )

                # Find and interact with search box
                logger.debug(f"Entering search query: {query}")
                search_selectors = [
                    "textarea[name='q']",
                    "input[name='q']",
                    "textarea[title='Search']",
                    "input[title='Search']",
                    "textarea[aria-label='Search']",
                    "input[aria-label='Search']",
                ]

                search_input = None
                for selector in search_selectors:
                    try:
                        search_input = await page.wait_for_selector(
                            selector, timeout=5000
                        )
                        logger.debug(f"Found search box with selector: {selector}")
                        break
                    except Exception:
                        logger.debug(f"Search box selector {selector} not found")
                        continue

                if not search_input:
                    raise GoogleSearchError("Could not find search input")

                # Type search query
                await search_input.click()
                await page.keyboard.type(
                    query, delay=random.randint(10, 30)  # noqa: S311
                )
                await asyncio.sleep(random.uniform(0.1, 0.3))  # noqa: S311
                await page.keyboard.press("Enter")

                logger.debug("Waiting for search results...")
                await page.wait_for_load_state("networkidle", timeout=timeout)

                # Check for post-search verification
                search_url = page.url
                if any(pattern in search_url for pattern in sorry_patterns):
                    if headless:
                        logger.warning(
                            "Post-search verification detected, retrying in headed mode..."
                        )
                        await page.close()
                        await context.close()
                        await browser.close()
                        return await _perform_search(headless=False)
                    logger.warning("Post-search verification detected, waiting...")
                    await page.wait_for_url(
                        lambda url: not any(
                            pattern in url for pattern in sorry_patterns
                        ),
                        timeout=timeout * 2,
                    )
                    await page.wait_for_load_state("networkidle", timeout=timeout)

                # Wait for search results
                result_selectors = ["#search", "#rso", ".g", "[data-sokoban-container]"]
                for selector in result_selectors:
                    try:
                        await page.wait_for_selector(selector, timeout=timeout // 2)
                        logger.debug(f"Found search results with selector: {selector}")
                        break
                    except Exception:
                        logger.debug(f"Search results selector {selector} not found")
                        continue

                await asyncio.sleep(random.uniform(0.2, 0.5))  # noqa: S311

                logger.debug("Extracting search results...")

                # Extract search results using JavaScript
                results = await page.evaluate(
                    f"""
                    (function() {{
                        const results = [];
                        const seenUrls = new Set();
                        const maxResults = {validated.max_results};

                        // Multiple selector strategies
                        const selectorSets = [
                            {{ container: '#search div[data-hveid]', title: 'h3', snippet: '.VwiC3b' }},
                            {{ container: '#rso div[data-hveid]', title: 'h3', snippet: '[data-sncf="1"]' }},
                            {{ container: '.g', title: 'h3', snippet: 'div[style*="webkit-line-clamp"]' }},
                            {{ container: 'div[jscontroller][data-hveid]', title: 'h3', snippet: 'div[role="text"]' }}
                        ];

                        const alternativeSnippetSelectors = [
                            '.VwiC3b', '[data-sncf="1"]', 'div[style*="webkit-line-clamp"]', 'div[role="text"]'
                        ];

                        for (const selectors of selectorSets) {{
                            if (results.length >= maxResults) break;

                            const containers = document.querySelectorAll(selectors.container);

                            for (const container of containers) {{
                                if (results.length >= maxResults) break;

                                const titleElement = container.querySelector(selectors.title);
                                if (!titleElement) continue;

                                const title = titleElement.textContent?.trim() || '';

                                // Find link
                                let link = '';
                                const linkInTitle = titleElement.querySelector('a');
                                if (linkInTitle) {{
                                    link = linkInTitle.href;
                                }} else {{
                                    let current = titleElement;
                                    while (current && current.tagName !== 'A') {{
                                        current = current.parentElement;
                                    }}
                                    if (current) {{
                                        link = current.href;
                                    }} else {{
                                        const containerLink = container.querySelector('a');
                                        if (containerLink) link = containerLink.href;
                                    }}
                                }}

                                if (!link || !link.startsWith('http') || seenUrls.has(link)) continue;

                                // Find snippet
                                let snippet = '';
                                const snippetElement = container.querySelector(selectors.snippet);
                                if (snippetElement) {{
                                    snippet = snippetElement.textContent?.trim() || '';
                                }} else {{
                                    for (const altSelector of alternativeSnippetSelectors) {{
                                        const element = container.querySelector(altSelector);
                                        if (element) {{
                                            snippet = element.textContent?.trim() || '';
                                            break;
                                        }}
                                    }}

                                    if (!snippet) {{
                                        const textNodes = Array.from(container.querySelectorAll('div')).filter(el =>
                                            !el.querySelector('h3') &&
                                            (el.textContent?.trim().length || 0) > 20
                                        );
                                        if (textNodes.length > 0) {{
                                            snippet = textNodes[0].textContent?.trim() || '';
                                        }}
                                    }}
                                }}

                                if (title && link) {{
                                    results.push({{ title, link, snippet }});
                                    seenUrls.add(link);
                                }}
                            }}
                        }}

                        return results.slice(0, maxResults);
                    }})()"""
                )

                logger.debug(f"Successfully extracted {len(results)} search results")

                # Save browser state
                if not no_save_state:
                    try:
                        logger.debug(f"Saving browser state to: {state_path}")
                        state_path.parent.mkdir(parents=True, exist_ok=True)
                        await context.storage_state(path=str(state_path))

                        # Save fingerprint configuration
                        with fingerprint_file.open("w", encoding="utf-8") as f:
                            json.dump(saved_state.dict(), f, indent=2)
                        logger.debug("Browser state and fingerprint saved successfully")
                    except Exception as e:
                        logger.error(f"Error saving browser state: {e}")

                # Convert results to proper format
                search_results = [
                    GoogleSearchResult(
                        title=result["title"],
                        link=result["link"],
                        snippet=result["snippet"],
                    )
                    for result in results
                ]

                return GoogleSearchResults(results=search_results)

            except Exception as e:
                logger.error(f"Error during search: {e}")

                # Try to save state even on error
                if not no_save_state:
                    try:
                        await context.storage_state(path=str(state_path))
                        with fingerprint_file.open("w", encoding="utf-8") as f:
                            json.dump(saved_state.dict(), f, indent=2)
                    except Exception:
                        logger.debug("Failed to save state on error")

                if (
                    "verification" in str(e).lower()
                    or "captcha" in str(e).lower()
                    and headless
                ):
                    logger.warning("Verification required, retrying in headed mode...")
                    return await _perform_search(headless=False)

                raise GoogleSearchError(f"Search failed: {e}") from e

            finally:
                import contextlib

                with contextlib.suppress(Exception):
                    await browser.close()

    try:
        # Start with headless mode
        return await _perform_search(headless=True)
    except PlaywrightTimeoutError as e:
        logger.error(f"Timeout during Google search: {e}")
        raise GoogleSearchError(f"Timeout during Google search: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during Google search: {e}")
        raise GoogleSearchError(f"Unexpected error during Google search: {e}") from e
