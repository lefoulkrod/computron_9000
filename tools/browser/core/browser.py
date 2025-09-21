"""Core Playwright browser utilities for agent tools.

This module provides a minimal, persistent Chromium context with small anti-bot tweaks
suited for LLM-powered browsing tools. It focuses on sensible defaults and clean
shutdown while keeping a light surface area.
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)

from config import load_config

if TYPE_CHECKING:  # Imported only for type checking to avoid runtime dependency surface
    from playwright.async_api import Geolocation, ProxySettings, ViewportSize

logger = logging.getLogger(__name__)

DEFAULT_UA = (
    # A realistic, stable Chromium UA (tweak as needed)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# Small jitter so every run isn't pixel-identical
def _viewport() -> ViewportSize:
    """Return a slightly jittered viewport size.

    This introduces small randomness so each run isn't pixel-identical, which
    can help reduce obvious automation signatures.

    Returns:
        A mapping compatible with Playwright's viewport format, containing
        ``width`` and ``height`` in pixels.
    """
    w = 1366 + secrets.choice(range(-8, 9))
    h = 768 + secrets.choice(range(-6, 7))
    return {"width": w, "height": h}


ANTI_BOT_INIT_SCRIPT = r"""
// --- Stealth patches to reduce automation detection ---

// 1) webdriver flag
Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => undefined });

// 2) languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// 3) platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// 4) chrome runtime object
window.chrome = window.chrome || { runtime: {} };

// 5) plugins
Object.defineProperty(navigator, 'plugins', {
  get: () => [1, 2, 3, 4, 5],
});

// 6) WebGL vendor/renderer
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
  if (parameter === 37445) return 'Intel Inc.';                  // UNMASKED_VENDOR_WEBGL
  if (parameter === 37446) return 'Intel(R) UHD Graphics';       // UNMASKED_RENDERER_WEBGL
  return getParameter.call(this, parameter);
};

// 7) Permissions API (avoid detection via notifications query)
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters);
"""


class Browser:
    """Minimal persistent Playwright browser core for powering LLM tools.

    Example:
        core = await CoreBrowser.start(profile_dir="~/.playwright/profiles/agent1")
        page = await core.new_page()
        await page.goto("https://example.com")
        ...
        await core.close()
    """

    def __init__(
        self,
        context: BrowserContext,
        extra_headers: dict[str, str] | None = None,
        pw: Playwright | None = None,
    ) -> None:
        """Initialize the browser wrapper.

        Args:
            context: The persistent Playwright browser context.
            extra_headers: Default HTTP headers applied to all requests.
            pw: The Playwright driver instance used to launch the context.
        """
        self._context: BrowserContext = context
        self._extra_headers: dict[str, str] = extra_headers or {}
        self._pw: Playwright | None = pw
        self._closed: bool = False

    @classmethod
    async def start(
        cls,
        profile_dir: str,
        *,
        headless: bool = False,
        user_agent: str = DEFAULT_UA,
        locale: str = "en-US",
        timezone_id: str = "America/Chicago",
        proxy: ProxySettings | None = None,
        accept_downloads: bool = True,
        geolocation: Geolocation | None = None,
        permissions: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
        args: list[str] | None = None,
    ) -> Browser:
        """Start a persistent Chromium context and return a ``Browser``.

        Args:
            profile_dir: Directory for Chromium user data (persisted across runs).
            headless: Whether to launch without a visible window.
            user_agent: User-Agent string to present to websites.
            locale: BCP 47 locale tag.
            timezone_id: IANA timezone ID to emulate.
            proxy: Optional proxy settings for the browser.
            accept_downloads: Whether to allow automatic downloads.
            geolocation: Optional geolocation to emulate.
            permissions: Optional list of permissions to grant to all pages.
            extra_headers: Additional default HTTP headers for all requests.
            args: Additional Chromium command-line flags.

        Returns:
            A ready-to-use ``Browser`` wrapping the persistent context.
        """
        profile_path = Path(profile_dir).expanduser().resolve()
        profile_path.mkdir(parents=True, exist_ok=True)

        # Chromium args tuned for stealth / stability
        chromium_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-features=AutomationControlled",
            "--start-maximized",
            "--disable-infobars",
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--ignore-certificate-errors",
        ]
        if args:
            chromium_args.extend(args)

        pw: Playwright = await async_playwright().start()
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=headless,
            proxy=proxy,
            args=chromium_args,
            viewport=_viewport(),
            user_agent=user_agent,
            locale=locale,
            timezone_id=timezone_id,
            accept_downloads=accept_downloads,
            geolocation=geolocation,
            permissions=permissions or [],
            java_script_enabled=True,  # ensure JS is enabled
        )

        # HTTP headers to look like a normal browser
        headers = {
            "Accept-Language": f"{locale},en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",  # 👈 important for GitHub
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            **(extra_headers or {}),
        }
        await context.set_extra_http_headers(headers)

        # Anti-bot JS shims
        await context.add_init_script(ANTI_BOT_INIT_SCRIPT)

        return cls(context=context, extra_headers=headers, pw=pw)

    async def new_page(self) -> Page:
        """Open a new page within the persistent context.

        Returns:
            The newly created Playwright ``Page``.
        """
        page = await self._context.new_page()
        await page.set_viewport_size(_viewport())
        # Small human-like delays for typing/clicking can be implemented in your tool layer
        return page

    async def current_page(self) -> Page:
        """Return the current page from the browser context.

        This selects the most recently opened, non-closed page from the
        underlying persistent ``BrowserContext``. If no such page exists,
        a new page is created, configured, and returned.

        Returns:
            Page: The active page to use for interactions.

        Raises:
            RuntimeError: If the browser has already been closed.
        """
        if self._closed:
            msg = "Browser context is closed; no current page available"
            raise RuntimeError(msg)

        # Prefer the most recently opened page that hasn't been closed.
        pages = self._context.pages  # Playwright provides a list[Page]
        for page in reversed(pages):
            # ``is_closed`` is a synchronous check in Playwright's async API
            if not page.is_closed():
                return page

        msg = "No open pages available in browser context"
        raise RuntimeError(msg)

    async def pages(self) -> list[Page]:
        """Return a snapshot list of all pages in the context.

        This provides a public, read-only style accessor so external tool
        helpers don't need to reach into the private ``_context`` attribute.

        Returns:
            list[Page]: Current pages (order: creation order as provided by Playwright).
        """
        return list(self._context.pages)

    async def context(self) -> BrowserContext:
        """Return the underlying persistent ``BrowserContext``."""
        return self._context

    async def close(self) -> None:
        """Close the browser context and stop the Playwright driver.

        This method is defensive: any exception raised while closing the
        underlying ``BrowserContext`` is logged and suppressed so that
        application shutdown can proceed cleanly. The method is idempotent
        and safe to call multiple times.
        """
        if self._closed:
            logger.debug("Browser.close called but already closed")
            return
        self._closed = True
        context_exc: Exception | None = None
        try:
            logger.debug("Closing Playwright BrowserContext ...")
            await self._context.close()
            logger.debug("BrowserContext closed")
        except PlaywrightError as exc:  # pragma: no cover - relies on Playwright internals
            # We store and log at warning level but do not re-raise; shutdown
            # should continue. The original error often appears when the
            # driver process exits first: e.g. "Connection closed while reading".
            context_exc = exc
            logger.warning(
                "Suppressed exception while closing BrowserContext: %s: %s",
                type(exc).__name__,
                exc,
            )
        except Exception as exc:  # noqa: BLE001  pragma: no cover - highly defensive
            # Non-Playwright exceptions (e.g. RuntimeError if driver already gone)
            context_exc = exc
            logger.warning(
                "Suppressed unexpected exception while closing BrowserContext: %s: %s",
                type(exc).__name__,
                exc,
            )
        finally:
            try:
                if self._pw is not None:
                    logger.debug("Stopping Playwright driver ...")
                    await self._pw.stop()
                    logger.debug("Playwright driver stopped")
            except PlaywrightError as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Suppressed exception while stopping Playwright driver: %s: %s",
                    type(exc).__name__,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001  pragma: no cover - highly defensive
                logger.warning(
                    "Suppressed unexpected exception while stopping Playwright driver: %s: %s",
                    type(exc).__name__,
                    exc,
                )
        # If there was an exception closing the context we intentionally swallow it.
        if context_exc:
            logger.debug("Browser.close completed with suppressed context exception")


_browser: Browser | None = None


async def get_browser() -> Browser:
    """Get the singleton browser instance, initializing it if necessary.

    Returns:
        _Browser: The persistent browser instance used for agent tools.
    """
    global _browser  # noqa: PLW0603
    if _browser is None:
        # initialize once and keep it for the lifetime of the process
        config = load_config()
        profile_path = Path(config.settings.home_dir) / "browser" / "profiles" / "default"
        _browser = await Browser.start(str(profile_path))
    return _browser


async def close_browser() -> None:
    """Shutdown the persistent browser instance if it exists.

    This function closes the browser context and resets the singleton instance.

    Returns:
        None
    """
    global _browser  # noqa: PLW0603
    if _browser is None:
        logger.debug("close_browser called but no browser instance exists")
        return
    try:
        await _browser.close()
    except PlaywrightError as exc:  # pragma: no cover - defensive
        # Should generally be handled inside Browser.close already, but we add
        # an outer guard in case of future changes.
        logger.warning(
            "Suppressed exception in close_browser wrapper: %s: %s", type(exc).__name__, exc
        )
    except Exception as exc:  # noqa: BLE001  pragma: no cover - highly defensive
        logger.warning(
            "Suppressed unexpected exception in close_browser wrapper: %s: %s",
            type(exc).__name__,
            exc,
        )
    finally:
        _browser = None
        logger.debug("Browser singleton cleared")
