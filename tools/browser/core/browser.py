"""Core Playwright browser utilities for agent tools.

This module provides a minimal, persistent Chromium context with small anti-bot tweaks
suited for LLM-powered browsing tools. It focuses on sensible defaults and clean
shutdown while keeping a light surface area.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from config import load_config

if TYPE_CHECKING:  # Imported only for type checking to avoid runtime dependency surface
    from playwright.async_api import Geolocation, ProxySettings, ViewportSize

DEFAULT_UA = (
    # A realistic, stable Chromium UA (tweak as needed)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
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
  // UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL
  if (parameter === 37445) return 'Intel Inc.';
  if (parameter === 37446) return 'Intel(R) UHD Graphics';
  return getParameter.call(this, parameter);
};
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
        timezone_id: str = "America/Chicago",  # matches your TZ
        proxy: ProxySettings | None = None,
        accept_downloads: bool = True,
        geolocation: Geolocation | None = None,  # {"latitude": 37.7749, "longitude": -122.4194}
        permissions: list[str] | None = None,  # e.g. ["geolocation", "clipboard-read", "clipboard-write"]
        extra_headers: dict[str, str] | None = None,  # sent with every request
        args: list[str] | None = None,  # extra Chromium args
    ) -> Browser:
        """Start a persistent Chromium context and return a ``CoreBrowser``.

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
            A ready-to-use ``CoreBrowser`` wrapping the persistent context.
        """
        # Expand and ensure profile directory exists
        profile_path = Path(profile_dir).expanduser().resolve()
        profile_path.mkdir(parents=True, exist_ok=True)

        # Reasonable Chromium args to look “normal” and suppress obvious automation
        chromium_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-features=AutomationControlled",
            "--start-maximized",
        ]
        if args:
            chromium_args.extend(args)

        # Start Playwright + PERSISTENT context (returns a BrowserContext directly)
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
        )

        # Extra HTTP headers (helps look like a real browser session)
        headers = {
            "Accept-Language": f"{locale},en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            **(extra_headers or {}),
        }
        await context.set_extra_http_headers(headers)

        # Anti-bot JS shims before any page runs its scripts
        await context.add_init_script(ANTI_BOT_INIT_SCRIPT)

        # Persisted context already acts like a single “browser”.
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

        # No existing usable page: create a new one.
        return await self.new_page()

    async def context(self) -> BrowserContext:
        """Return the underlying persistent ``BrowserContext``."""
        return self._context

    async def close(self) -> None:
        """Close the browser context and stop the Playwright driver."""
        if self._closed:
            return
        self._closed = True
        try:
            await self._context.close()
        finally:
            # Stop Playwright driver
            if self._pw is not None:
                await self._pw.stop()


_browser: Browser | None = None


async def get_browser() -> Browser:
    """Get the singleton browser instance, initializing it if necessary.

    Returns:
        _Browser: The persistent browser instance used for agent tools.
    """
    global _browser
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
    global _browser
    if _browser is not None:
        await _browser.close()
        _browser = None
