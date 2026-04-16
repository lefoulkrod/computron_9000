"""Core Playwright browser utilities for agent tools.

This module provides a minimal, persistent Chromium context with small anti-bot tweaks
suited for LLM-powered browsing tools. It focuses on sensible defaults and clean
shutdown while keeping a light surface area.
"""

from __future__ import annotations

import atexit
import asyncio
import time
import logging
import os
import secrets
import signal
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from playwright.async_api import (
    BrowserContext,
    Frame,
    Page,
    Playwright,
    Response,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, ConfigDict

import tools.browser.core.waits as browser_waits
from config import load_config
from tools.browser.core._file_detection import DownloadInfo
from urllib.parse import urlparse

if TYPE_CHECKING:  # Imported only for type checking to avoid runtime dependency surface
    from playwright.async_api import Geolocation, ProxySettings, ViewportSize

# Union type for functions that can operate on either a Page or a Frame.
# Frame exposes the same DOM-query API as Page (evaluate, locator, get_by_role,
# get_by_text, etc.) but lacks mouse/keyboard and screenshot methods.
PageOrFrame = Page | Frame


class ActiveView(NamedTuple):
    """Snapshot of the current browser view for tools to operate on.

    Tools should call ``Browser.active_view()`` instead of ``current_page()``
    or ``active_frame()`` directly.  The ``frame`` is whichever context the
    tool should interact with (iframe if dominant, otherwise the main page).
    ``title`` and ``url`` always come from the main page so the agent sees
    a consistent identity regardless of iframes.
    """

    frame: Page | Frame
    title: str
    url: str

logger = logging.getLogger(__name__)


def _extract_registered_domain(url: str) -> str:
    """Extract the registered domain from a URL.

    Handles common URL patterns and strips subdomains to return the
    base registered domain (e.g. "www.google.com" → "google.com",
    "l.facebook.com" → "facebook.com").

    Args:
        url: A URL string to extract the domain from.

    Returns:
        The registered domain string, or empty string if extraction fails.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not hostname:
            return ""
        parts = hostname.split(".")
        # Handle common TLDs with two-part suffixes (co.uk, com.au, etc.)
        # and standard single-part TLDs.  For simplicity, return the last
        # two parts for most cases which covers the vast majority of
        # registered domains.
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return hostname
    except Exception:
        return ""


# Small jitter so every run isn't pixel-identical
def _viewport() -> ViewportSize:
    """Return a slightly jittered viewport size.

    This introduces small randomness so each run isn't pixel-identical, which
    can help reduce obvious automation signatures.

    Returns:
        A mapping compatible with Playwright's viewport format, containing
        ``width`` and ``height`` in pixels.
    """
    w = 1920 + secrets.choice(range(-8, 9))
    h = 1080 + secrets.choice(range(-6, 7))
    return {"width": w, "height": h}


# ---------------------------------------------------------------------------
# Shared helper injected into both stealth scripts
# ---------------------------------------------------------------------------

_MAKE_NATIVE_JS = r"""
// Helper: make a replaced function's .toString() return a native code string.
// Handles the common check: fn.toString() and fn.toString.toString().
// Note: Function.prototype.toString.call(fn) will still reveal the real source,
// but virtually no bot detection does this check.
const _makeNative = (fn, nativeName) => {
  const toStr = `function ${nativeName}() { [native code] }`;
  const toString = () => toStr;
  Object.defineProperty(toString, 'toString', {
    value: () => 'function toString() { [native code] }',
    configurable: true, writable: false,
  });
  Object.defineProperty(fn, 'toString', {
    value: toString, configurable: true, writable: false,
  });
  return fn;
};
"""

# ---------------------------------------------------------------------------
# The only patch needed for real Chrome: remove the webdriver property so
# navigator.webdriver is undefined, matching a real non-automated browser.
# --disable-blink-features=AutomationControlled prevents Playwright from
# injecting navigator.webdriver=true via CDP, so deleting the native C++
# getter (which returns false with that flag) leaves the property fully absent.
# Redefining it as false is detectable — fp-collect checks for the property's
# existence, not just its value.
# ---------------------------------------------------------------------------

_ANTI_BOT_SCRIPT = (
    "// --- Stealth patches to reduce automation detection ---\n"
    + _MAKE_NATIVE_JS
    + r"""
// webdriver flag — delete it entirely so navigator.webdriver is undefined.
// In a real non-automated Chrome the property does not exist at all.
// --disable-blink-features=AutomationControlled prevents Playwright from
// re-injecting it, so it is safe to leave it absent.
delete Navigator.prototype.webdriver;
delete navigator.webdriver;

// WebGL — ensure getContext returns valid contexts so WebGL-dependent
// sites (maps, 3D) work and bot detectors don't flag missing WebGL.
const _origGetContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, ...args) {
  if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
    const ctx = _origGetContext.call(this, type, ...args);
    if (ctx) return ctx;
    // Fallback: try creating with basic attributes
    return _origGetContext.call(this, type, { ...args[0], failIfMajorPerformanceCaveat: false });
  }
  return _origGetContext.call(this, type, ...args);
};

// Permissions — override navigator.permissions.query so sites that check
// for notification/geolocation permissions don't see the default "prompt"
// state that headless Chrome reports.
const _origQuery = Permissions.prototype.query;
Permissions.prototype.query = function(parameters) {
  if (parameters.name === 'notifications') {
    return Promise.resolve({ state: 'denied', onchange: null });
  }
  return _origQuery.call(this, parameters);
};
_makeNative(Permissions.prototype.query, 'query');
"""
)

# Force all shadow DOM attachments to use open mode so the DOM walker
# in page_view.py can traverse shadow roots.  Closed shadow roots
# return null from el.shadowRoot, making their contents invisible to
# JavaScript-based DOM walkers.  Playwright's own locators already
# pierce closed shadow DOM via CDP, so interactions still work — this
# patch only affects snapshot visibility.
_OPEN_SHADOW_DOM_SCRIPT = r"""
(function() {
  const _origAttachShadow = Element.prototype.attachShadow;
  Element.prototype.attachShadow = function(opts) {
    return _origAttachShadow.call(this, { ...opts, mode: 'open' });
  };
})();
"""

class BrowserInteractionResult(BaseModel):
    """Structured metadata describing the outcome of a browser interaction."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    navigation_response: Response | None = None
    download: DownloadInfo | None = None
    settle_timings: browser_waits.SettleTimings | None = None
    frame_transition: str | None = None
    action_ms: float = 0.0
    redirect_warning: str | None = None


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
        pw_browser: Any = None,
        profile_dir: str = "",
    ) -> None:
        """Initialize the browser wrapper.

        Args:
            context: The Playwright browser context.
            extra_headers: Default HTTP headers applied to all requests.
            pw: The Playwright driver instance used to launch the browser.
            pw_browser: The Playwright Browser object. Present on the root
                browser so sub-agents can create new contexts on it.
            profile_dir: Path to the browser session state directory.
        """
        self._context: BrowserContext = context
        self._profile_dir: str = profile_dir
        self._extra_headers: dict[str, str] = extra_headers or {}
        self._pw: Playwright | None = pw
        self._pw_browser: Any = pw_browser
        self._closed: bool = False
        self._active_frame: Frame | None = None
        self._pending_downloads: list[DownloadInfo] = []
        self._downloads_dir: str = ""
        self._download_listener_pages: set[int] = set()  # page id() tracking
        self._download_tasks: set[asyncio.Task[None]] = set()
        self._download_event: asyncio.Event = asyncio.Event()

        # Auto-attach download listeners to pages created by popups or
        # target=_blank links so file downloads in new tabs are captured.
        self._context.on("page", self._on_context_page)

        # Capture the Playwright driver PID so the atexit handler can kill the
        # process tree if the async close path never ran (e.g. SIGKILL, event
        # loop torn down before shutdown hooks complete).
        self._driver_pid: int | None = None
        try:
            transport = pw._impl_obj._connection._transport  # type: ignore[union-attr]
            proc = getattr(transport, "_proc", None)
            if proc:
                self._driver_pid = proc.pid
        except Exception:  # noqa: BLE001
            pass

    def _attach_download_listener(self, page: Page) -> None:
        """Attach a download event listener to a page if not already attached."""
        page_id = id(page)
        if page_id in self._download_listener_pages:
            return
        self._download_listener_pages.add(page_id)

        def _on_download(download: Any) -> None:
            task = asyncio.ensure_future(self._handle_download(download))
            self._download_tasks.add(task)
            task.add_done_callback(self._download_tasks.discard)

        page.on("download", _on_download)

    def _on_context_page(self, page: Page) -> None:
        """Handle new pages created by popups or ``target=_blank`` links.

        Immediately attaches a download listener so file downloads in the
        new tab are captured by ``_pending_downloads``.
        """
        self._attach_download_listener(page)

    async def _handle_download(self, download: Any) -> None:
        """Process a Playwright download event and record the result."""
        try:
            path = await download.path()
            if not path:
                logger.warning("Download completed but no path available")
                return

            # Playwright saves downloads with opaque UUID filenames.  Rename
            # to the server's suggested name so the agent sees a meaningful
            # filename and MIME-type detection works correctly.
            suggested: str = getattr(download, "suggested_filename", "")
            if suggested and self._downloads_dir:
                dest = Path(self._downloads_dir) / suggested
                if dest.exists():
                    stem, suffix = dest.stem, dest.suffix
                    suggested = f"{stem}_{secrets.token_hex(4)}{suffix}"
                    dest = Path(self._downloads_dir) / suggested
                try:
                    Path(path).rename(dest)
                    path = str(dest)
                except OSError:
                    logger.debug("Could not rename download to %s", suggested)

            from tools.browser.core._file_detection import build_download_info_from_path

            info = build_download_info_from_path(path)
            self._pending_downloads.append(info)
            self._download_event.set()
            logger.info(
                "Download captured: %s (%s, %d bytes)",
                info.filename, info.content_type, info.size_bytes,
            )
        except Exception:
            logger.exception("Failed to process download event")

    def drain_downloads(self) -> list[DownloadInfo]:
        """Return and clear any pending downloads captured since the last drain."""
        downloads = list(self._pending_downloads)
        self._pending_downloads.clear()
        return downloads

    @classmethod
    async def start(
        cls,
        profile_dir: str,
        *,
        headless: bool = False,
        locale: str = "en-US",
        timezone_id: str = "America/Chicago",
        proxy: ProxySettings | None = None,
        accept_downloads: bool = True,
        downloads_path: str | None = None,
        geolocation: Geolocation | None = None,
        permissions: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
        args: list[str] | None = None,
    ) -> Browser:
        """Launch system Chrome and create a browser context.

        Uses ``chromium.launch()`` which returns a ``Browser`` object,
        allowing sub-agents to create additional contexts on the same
        Chrome process via ``_pw_browser``.

        Session state (cookies, localStorage) is persisted to a JSON file
        in *profile_dir* and restored on the next launch.

        Args:
            profile_dir: Directory for session state persistence.
            headless: Whether to launch without a visible window.
            locale: BCP 47 locale tag.
            timezone_id: IANA timezone ID to emulate.
            proxy: Optional proxy settings for the browser.
            accept_downloads: Whether to allow automatic downloads.
            downloads_path: Directory where downloaded files are saved.
            geolocation: Optional geolocation to emulate.
            permissions: Optional list of permissions to grant to all pages.
            extra_headers: Additional default HTTP headers for all requests.
            args: Additional Chromium command-line flags.

        Returns:
            A ready-to-use ``Browser`` wrapping the context.
        """
        profile_path = Path(profile_dir).expanduser().resolve()
        profile_path.mkdir(parents=True, exist_ok=True)

        chrome_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=AutomationControlled",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            *(["--start-maximized"] if not headless else []),
            "--enable-automation=false",
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--disable-pdf-viewer",
            "--enable-webgl",
            "--enable-webgl2-compute-context",
            "--disable-features=TranslateUI",
            "--disable-features=OptimizationGuideModelDownloading",
        ]
        if args:
            chrome_args.extend(args)

        resolved_downloads_path: str | None = None
        if downloads_path:
            dl_path = Path(downloads_path).expanduser().resolve()
            dl_path.mkdir(parents=True, exist_ok=True)
            resolved_downloads_path = str(dl_path)

        viewport = _viewport()

        launch_kwargs: dict[str, Any] = dict(
            channel="chrome",
            headless=headless,
            args=chrome_args,
        )
        if resolved_downloads_path:
            launch_kwargs["downloads_path"] = resolved_downloads_path

        pw: Playwright = await async_playwright().start()
        try:
            pw_browser = await pw.chromium.launch(**launch_kwargs)
        except Exception:
            try:
                await asyncio.wait_for(pw.stop(), timeout=5.0)
            except Exception:  # noqa: BLE001
                pass
            pw = await async_playwright().start()
            try:
                pw_browser = await pw.chromium.launch(**launch_kwargs)
            except Exception:
                await pw.stop()
                raise

        # Restore session state (cookies + localStorage) from previous run.
        state_file = profile_path / "storage_state.json"
        storage_state: Any = None
        if state_file.exists():
            try:
                storage_state = str(state_file)
                logger.info("Restoring browser session from %s", state_file)
            except Exception:  # noqa: BLE001
                logger.warning("Failed to load browser storage state")

        context_kwargs: dict[str, Any] = dict(
            viewport=viewport,
            locale=locale,
            timezone_id=timezone_id,
            accept_downloads=accept_downloads,
            geolocation=geolocation,
            permissions=permissions or [],
            java_script_enabled=True,
            storage_state=storage_state,
        )
        if proxy:
            context_kwargs["proxy"] = proxy

        context = await pw_browser.new_context(**context_kwargs)

        headers = {
            "Accept-Language": "%s,en;q=0.9" % locale,
            **(extra_headers or {}),
        }
        await context.set_extra_http_headers(headers)

        await context.add_init_script(_ANTI_BOT_SCRIPT)
        await context.add_init_script(_OPEN_SHADOW_DOM_SCRIPT)

        return cls(
            context=context,
            extra_headers=headers,
            pw=pw,
            pw_browser=pw_browser,
            profile_dir=str(profile_path),
        )

    @classmethod
    async def start_ephemeral(
        cls,
        root_browser: Browser,
        storage_state: Any,
    ) -> Browser:
        """Create an ephemeral browser context on the root's Chrome process.

        The new context inherits cookies and localStorage from *storage_state*
        but is fully isolated — changes do not affect the root profile or other
        ephemeral contexts.

        Args:
            root_browser: The root browser whose ``_pw_browser`` hosts the
                new context. Also used as template for headers and anti-bot
                patches.
            storage_state: Cookies and localStorage snapshot from
                ``root_browser._context.storage_state()``.

        Returns:
            A ``Browser`` wrapping the new ephemeral context.
        """
        context = await root_browser._pw_browser.new_context(
            storage_state=storage_state,
            viewport=_viewport(),
            locale="en-US",
            timezone_id="America/Chicago",
            accept_downloads=True,
            java_script_enabled=True,
        )

        # Apply the same HTTP headers and anti-bot patches as the root.
        headers = dict(root_browser._extra_headers)
        await context.set_extra_http_headers(headers)
        await context.add_init_script(_ANTI_BOT_SCRIPT)
        await context.add_init_script(_OPEN_SHADOW_DOM_SCRIPT)

        instance = cls(
            context=context,
            extra_headers=headers,
            pw=None,  # ephemeral — does not own the Playwright driver
            profile_dir="",
        )
        instance._downloads_dir = root_browser._downloads_dir
        return instance

    async def close_context(self) -> None:
        """Close only the browser context, not the Playwright driver.

        Used for ephemeral sub-agent contexts that share the root's Chromium
        process.  The ``close()`` method is inappropriate here because it also
        stops the Playwright driver, which would kill the shared process.
        """
        if self._closed:
            return
        self._closed = True
        for page in list(self._context.pages):
            try:
                if not page.is_closed():
                    await asyncio.wait_for(page.close(), timeout=3.0)
            except Exception:  # noqa: BLE001
                pass
        try:
            await asyncio.wait_for(self._context.close(), timeout=5.0)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to close ephemeral browser context")

    async def new_page(self) -> Page:
        """Open a new page within the persistent context.

        Returns:
            The newly created Playwright ``Page``.
        """
        page = await self._context.new_page()
        await page.set_viewport_size(_viewport())
        self._attach_download_listener(page)
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
                self._attach_download_listener(page)
                return page

        msg = "No open pages available in browser context"
        raise RuntimeError(msg)

    async def active_frame(self) -> Page | Frame:
        """Return the dominant iframe if one is active, otherwise the current page.

        When a large iframe (e.g. a booking widget overlay) covers a significant
        portion of the viewport, all DOM-reading tools should operate on that
        iframe instead of the main frame.  This method transparently returns
        whichever context the tools should use.

        Returns:
            The active ``Frame`` if a dominant iframe is tracked and still
            attached, otherwise the current ``Page``.
        """
        if self._active_frame is not None:
            if self._active_frame.is_detached():
                logger.debug("Active frame detached; falling back to page")
                self._active_frame = None
            else:
                return self._active_frame
        return await self.current_page()

    def clear_active_frame(self) -> None:
        """Reset the active frame so tools operate on the main page."""
        self._active_frame = None

    async def active_view(self) -> ActiveView:
        """Return an ``ActiveView`` for tools to operate on.

        Proactively detects a dominant iframe if none is currently tracked.
        Reuses an already-set ``_active_frame`` without re-detecting.
        Title and URL always come from the main page.
        """
        page = await self.current_page()

        if self._active_frame is not None and not self._active_frame.is_detached():
            frame: Page | Frame = self._active_frame
        else:
            self._active_frame = None
            try:
                dominant = await self._detect_dominant_frame(page)
                if dominant is not None:
                    self._active_frame = dominant
                    frame = dominant
                else:
                    frame = page
            except Exception:  # noqa: BLE001 - detection is best-effort
                frame = page

        try:
            title = await page.title()
        except PlaywrightError:
            title = ""

        return ActiveView(frame=frame, title=title, url=page.url)

    # Minimum fraction of viewport area an iframe must cover to become dominant.
    _DOMINANT_FRAME_THRESHOLD = 0.25

    async def _detect_dominant_frame(self, page: Page) -> Frame | None:
        """Find an iframe covering a large portion of the viewport.

        Iterates all frames on the page, skips the main frame and detached
        frames, measures each frame element's bounding box, and returns the
        largest accessible frame that covers more than 25% of the viewport.

        Returns:
            The dominant ``Frame``, or ``None`` if no qualifying frame exists.
        """
        viewport = page.viewport_size
        if not viewport:
            return None
        vw, vh = viewport["width"], viewport["height"]
        min_area = vw * vh * self._DOMINANT_FRAME_THRESHOLD

        best_frame: Frame | None = None
        best_area: float = 0

        for frame in page.frames:
            if frame == page.main_frame:
                continue
            if frame.is_detached():
                continue
            try:
                element = await frame.frame_element()
                box = await element.bounding_box()
            except Exception:  # noqa: BLE001 - skip inaccessible frames
                continue
            if box is None:
                continue

            area = box["width"] * box["height"]
            if area < min_area:
                continue

            # Verify the frame has accessible, meaningful content — not
            # just an ad iframe with images/scripts but no real UI.
            try:
                content_check = await frame.evaluate(
                    """() => {
                        if (!document.body) return { children: 0, text: 0, interactive: 0 };
                        return {
                            children: document.body.children.length,
                            text: (document.body.innerText || '').trim().length,
                            interactive: document.body.querySelectorAll(
                                'a[href], button, input, select, textarea'
                            ).length,
                        };
                    }"""
                )
                has_content = (
                    content_check["children"] > 0
                    and (content_check["text"] > 0 or content_check["interactive"] > 3)
                )
                if has_content and area > best_area:
                    best_frame = frame
                    best_area = area
            except Exception:  # noqa: BLE001 - cross-origin or detached
                continue

        return best_frame

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

    @staticmethod
    def _unwrap_tracking_url(url: str) -> str:
        """Unwrap tracking redirect URLs to get the actual destination.

        Handles common tracking redirect patterns:
        - l.facebook.com/l.php?u=<encoded_url>
        - lm.facebook.com/l.php?u=<encoded_url>
        """
        from urllib.parse import parse_qs as _parse_qs

        try:
            parsed = urlparse(url)
            # Facebook tracking redirects
            if parsed.hostname in ("l.facebook.com", "lm.facebook.com"):
                qs = _parse_qs(parsed.query)
                if "u" in qs and qs["u"]:
                    return qs["u"][0]
        except Exception:
            pass
        return url

    async def navigate(self, url: str) -> BrowserInteractionResult:
        """Navigate to *url* and return a ``BrowserInteractionResult``."""
        try:
            page = await self.current_page()
        except RuntimeError:
            page = await self.new_page()
        self.clear_active_frame()
        self._pending_downloads.clear()
        initial_url = getattr(page, "url", "")

        # Unwrap tracking redirect URLs before navigation (BTI-017)
        unwrapped_url = self._unwrap_tracking_url(url)
        if unwrapped_url != url:
            logger.info("Unwrapped tracking URL: %s -> %s", url, unwrapped_url)
            url = unwrapped_url

        try:
            response = await page.goto(url, wait_until="domcontentloaded")
        except PlaywrightError as exc:
            # When --disable-pdf-viewer converts a navigation to a download,
            # Chromium aborts the page load with net::ERR_ABORTED.  The
            # download listener captures the file asynchronously — wait
            # for the download event before falling through to finalize.
            if "net::ERR_ABORTED" not in str(exc):
                raise
            logger.debug("Navigation aborted (likely download): %s", url)
            response = None
            try:
                await page.wait_for_event("download", timeout=5_000)
            except (PlaywrightTimeoutError, PlaywrightError):
                pass

        # Detect cross-domain redirects (BTI-001, BTI-003, etc.)
        redirect_warning = None
        try:
            intended_domain = _extract_registered_domain(url)
            final_domain = _extract_registered_domain(page.url)
            if intended_domain and final_domain and intended_domain != final_domain:
                redirect_warning = (
                    "Cross-domain redirect detected: intended %s, "
                    "landed on %s. This may indicate session contamination "
                    "or DNS issues. Original URL: %s"
                ) % (intended_domain, final_domain, url)
                logger.warning(
                    "Cross-domain redirect: %s -> %s (intended: %s)",
                    url, page.url, intended_domain,
                )
        except Exception:
            pass  # Best-effort detection

        return await self._finalize_action(
            page, response=response, initial_url=initial_url,
            redirect_warning=redirect_warning,
        )

    async def navigate_back(self) -> BrowserInteractionResult:
        """Navigate back in history via ``perform_interaction``."""
        page = await self.current_page()

        async def _back() -> None:
            try:
                await asyncio.wait_for(
                    page.go_back(wait_until="domcontentloaded"),
                    timeout=10.0,
                )
            except (asyncio.TimeoutError, PlaywrightError):
                # SPA may handle back navigation client-side without firing
                # domcontentloaded. Fall through to settle/snapshot.
                logger.debug("go_back timed out (SPA likely handled navigation client-side)")

        return await self.perform_interaction(_back)

    # Timeouts for individual shutdown steps.  These are generous enough for
    # well-behaved pages but prevent indefinite hangs when Chromium is stuck.
    _PAGE_CLOSE_TIMEOUT_S: float = 3.0
    _CONTEXT_CLOSE_TIMEOUT_S: float = 5.0
    _PW_STOP_TIMEOUT_S: float = 5.0

    async def close(self) -> None:
        """Close the browser context and stop the Playwright driver.

        Each shutdown step (page close, context close, driver stop) is guarded
        by a timeout so that a hung Chromium process cannot block the caller
        indefinitely.  Stopping the Playwright driver (the last step) kills its
        subprocess which also terminates the browser, so even if the earlier
        steps time out the browser is cleaned up.

        The method is idempotent and safe to call multiple times.
        """
        if self._closed:
            logger.debug("Browser.close called but already closed")
            return
        self._closed = True

        # Persist session state (cookies + localStorage) so the next launch
        # can restore login sessions.
        if self._profile_dir:
            state_file = Path(self._profile_dir) / "storage_state.json"
            try:
                await self._context.storage_state(path=str(state_file))
                logger.info("Saved browser session state to %s", state_file)
            except Exception:  # noqa: BLE001
                logger.warning("Failed to save browser storage state")

        context_exc: Exception | None = None
        pages_to_close = list(self._context.pages)
        for page in pages_to_close:
            try:
                if getattr(page, "is_closed", lambda: False)():
                    continue
            except Exception:  # noqa: BLE001 - treat unknown failures as closed
                continue
            try:
                logger.debug("Closing page %s before shutdown", getattr(page, "url", "<unknown>"))
                await asyncio.wait_for(page.close(), timeout=self._PAGE_CLOSE_TIMEOUT_S)
            except asyncio.TimeoutError:
                logger.warning("Timed out closing page %s — proceeding", getattr(page, "url", "<unknown>"))
            except PlaywrightError as exc:  # pragma: no cover - defensive
                logger.debug("Suppressed exception while closing page: %s: %s", type(exc).__name__, exc)
            except Exception as exc:  # noqa: BLE001  pragma: no cover - highly defensive
                logger.debug("Unexpected exception while closing page: %s: %s", type(exc).__name__, exc)
        try:
            logger.debug("Closing Playwright BrowserContext ...")
            await asyncio.wait_for(self._context.close(), timeout=self._CONTEXT_CLOSE_TIMEOUT_S)
            logger.debug("BrowserContext closed")
        except asyncio.TimeoutError:
            context_exc = TimeoutError("BrowserContext.close() timed out")
            logger.warning(
                "Timed out closing BrowserContext after %.1fs — will force-stop driver",
                self._CONTEXT_CLOSE_TIMEOUT_S,
            )
        except PlaywrightError as exc:  # pragma: no cover - relies on Playwright internals
            context_exc = exc
            logger.warning(
                "Suppressed exception while closing BrowserContext: %s: %s",
                type(exc).__name__,
                exc,
            )
        except Exception as exc:  # noqa: BLE001  pragma: no cover - highly defensive
            context_exc = exc
            logger.warning(
                "Suppressed unexpected exception while closing BrowserContext: %s: %s",
                type(exc).__name__,
                exc,
            )
        finally:
            # Close the Playwright Browser (kills Chrome), then stop the driver.
            try:
                if self._pw_browser is not None:
                    logger.debug("Closing Playwright Browser ...")
                    await asyncio.wait_for(self._pw_browser.close(), timeout=self._CONTEXT_CLOSE_TIMEOUT_S)
                    logger.debug("Playwright Browser closed")
            except Exception:  # noqa: BLE001
                logger.warning("Failed to close Playwright Browser")
            try:
                if self._pw is not None:
                    logger.debug("Stopping Playwright driver ...")
                    await asyncio.wait_for(self._pw.stop(), timeout=self._PW_STOP_TIMEOUT_S)
                    logger.debug("Playwright driver stopped")
            except asyncio.TimeoutError:
                logger.warning(
                    "Timed out stopping Playwright driver after %.1fs",
                    self._PW_STOP_TIMEOUT_S,
                )
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

        if context_exc:
            logger.debug("Browser.close completed with suppressed context exception")

    async def _finalize_action(
        self,
        page: Page,
        *,
        response: Response | None,
        initial_url: str,
        saw_download_response: bool = False,
        redirect_warning: str | None = None,
    ) -> BrowserInteractionResult:
        """Shared post-action pipeline: downloads, settle, iframe detection, logging."""
        wait_cfg = load_config().tools.browser.waits

        # 1. Download detection
        download_info: DownloadInfo | None = None

        if self._download_tasks:
            await asyncio.gather(*self._download_tasks, return_exceptions=True)

        pending = self.drain_downloads()
        if pending:
            download_info = pending[0]

        if download_info is None and response is not None:
            from tools.browser.core._file_detection import (
                is_file_content_type,
                save_response_as_file,
            )
            ct = response.headers.get("content-type", "")
            if is_file_content_type(ct):
                try:
                    download_info = await save_response_as_file(
                        response,
                        downloads_dir=self._downloads_dir or ".",
                    )
                except Exception:
                    logger.exception("Failed to save file from response")

        # 2. Settle (skip if download — no page to settle)
        settle_timings = None
        if download_info is None:
            try:
                settle_timings = await browser_waits.wait_for_page_settle(page, waits=wait_cfg)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Page settle raised unexpectedly: %s", exc)

            # Re-check for downloads that arrived during page settle.
            # This catches same-tab redirect chains to PDFs (e.g. Bing
            # click-through → prier.com/document.pdf) where the download
            # event fires after the initial check but during settle.
            if self._download_tasks:
                await asyncio.gather(*self._download_tasks, return_exceptions=True)
            late_downloads = self.drain_downloads()
            if late_downloads:
                download_info = late_downloads[0]

        # 2b. If we saw a Content-Disposition: attachment response but the
        # Playwright download event hasn't fired yet, wait for it.  This
        # only triggers when an attachment header was observed — zero cost
        # on normal interactions.
        if download_info is None and saw_download_response:
            try:
                await asyncio.wait_for(self._download_event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.debug("Download grace period expired despite attachment header")
            if self._download_tasks:
                await asyncio.gather(*self._download_tasks, return_exceptions=True)
            grace_downloads = self.drain_downloads()
            if grace_downloads:
                download_info = grace_downloads[0]
                logger.info(
                    "Late download captured after attachment response: %s",
                    download_info.filename,
                )

        # 3. Iframe detection (skip if download — page may be a PDF viewer stub)
        frame_transition: str | None = None
        final_url = getattr(page, "url", initial_url)

        # Handle about:blank transitional pages (BTI-023)
        if final_url == "about:blank" and initial_url and initial_url != "about:blank":
            try:
                # Wait for the actual page to load after about:blank
                await page.wait_for_url(lambda u: u != "about:blank", timeout=3000)
                final_url = getattr(page, "url", initial_url)
            except (PlaywrightTimeoutError, PlaywrightError):
                logger.debug("Page remained at about:blank after wait; proceeding")

        navigated = bool(initial_url and final_url and final_url != initial_url)

        if download_info is not None:
            self._active_frame = None
        elif navigated:
            self._active_frame = None
        else:
            try:
                previous_frame = self._active_frame
                dominant = await self._detect_dominant_frame(page)
                if dominant != self._active_frame:
                    if dominant is not None:
                        frame_transition = f"→ iframe {dominant.url}"
                    elif self._active_frame is not None:
                        frame_transition = "→ main page"
                    self._active_frame = dominant

                if dominant is not None and dominant != previous_frame:
                    try:
                        await dominant.wait_for_load_state("load", timeout=5000)
                        await browser_waits.wait_for_page_settle(dominant, waits=wait_cfg)
                    except (PlaywrightTimeoutError, PlaywrightError):
                        pass
            except Exception:  # noqa: BLE001
                logger.debug("Dominant frame detection failed; keeping current state")

        return BrowserInteractionResult(
            navigation_response=response,
            download=download_info,
            settle_timings=settle_timings,
            frame_transition=frame_transition,
            redirect_warning=redirect_warning,
        )

    async def _probe_file_url(self, new_page: Page, url: str) -> Page | None:
        """Probe a new tab's URL to check if it's a file download.

        Chrome's PDF viewer extension (non-headless) can silently handle file
        URLs without firing Playwright response or download events.  This
        method fetches the URL directly via the API request context, saves
        the file if it's a non-HTML content-type, and appends a
        ``DownloadInfo`` to ``_pending_downloads``.

        Returns the new page if a file was saved, or ``None`` to stay on the
        original page.
        """
        from tools.browser.core._file_detection import (
            is_file_content_type,
            save_response_as_file,
        )

        try:
            api_resp = await asyncio.wait_for(
                self._context.request.get(url), timeout=15.0,
            )
            ct = api_resp.headers.get("content-type", "")
            if is_file_content_type(ct):
                info = await save_response_as_file(
                    api_resp,
                    downloads_dir=self._downloads_dir or ".",
                )
                self._pending_downloads.append(info)
                logger.info(
                    "Probed file URL in new tab: %s (%s, %d bytes)",
                    info.filename, info.content_type, info.size_bytes,
                )
                await api_resp.dispose()
                return new_page
            await api_resp.dispose()
        except Exception:  # noqa: BLE001
            logger.debug("Failed to probe new tab URL: %s", url)
        return None

    async def perform_interaction(
        self,
        action: Callable[[], Awaitable[Any]],
    ) -> BrowserInteractionResult:
        """Perform an interaction and run the shared post-action pipeline."""
        page = await self.current_page()
        initial_url = getattr(page, "url", "")

        self._pending_downloads.clear()
        self._download_event.clear()
        captured_responses: list[Response] = []

        # Track pages opened during this interaction (popups / target=_blank)
        # and capture their document responses so file downloads in new tabs
        # are detected properly.
        new_pages: list[Page] = []
        new_page_responses: list[Response] = []
        _np_listeners: list[tuple[Page, Callable[..., Any]]] = []

        _saw_download_response = False

        def _on_response(resp: Response) -> None:
            nonlocal _saw_download_response
            if resp.frame == page.main_frame and resp.request.resource_type == "document":
                captured_responses.append(resp)
            # Detect responses that will trigger a download event.  The
            # browser converts these to downloads asynchronously, so the
            # Playwright download event fires after a short delay.
            disposition = resp.headers.get("content-disposition", "")
            if "attachment" in disposition:
                _saw_download_response = True

        def _on_new_page(new_page: Page) -> None:
            new_pages.append(new_page)

            def _on_np_response(resp: Response) -> None:
                if resp.request.resource_type == "document":
                    new_page_responses.append(resp)

            new_page.on("response", _on_np_response)
            _np_listeners.append((new_page, _on_np_response))

        page.on("response", _on_response)
        self._context.on("page", _on_new_page)

        t0 = time.monotonic()
        await action()
        action_ms = (time.monotonic() - t0) * 1000

        from tools.browser.events import flush_progressive_screenshot
        await flush_progressive_screenshot()

        page.remove_listener("response", _on_response)
        self._context.remove_listener("page", _on_new_page)

        response = captured_responses[-1] if captured_responses else None
        target_page = page

        # If a new tab opened and the original page had no document response,
        # the click likely opened a file (PDF, etc.) in a new tab.  Wait for
        # the new page to finish its navigation, then use its response so
        # _finalize_action can detect the file download.
        if new_pages and response is None:
            new_page = new_pages[-1]
            if not new_page_responses:
                try:
                    await new_page.wait_for_load_state(
                        "domcontentloaded", timeout=10_000,
                    )
                except (PlaywrightTimeoutError, PlaywrightError):
                    pass
            if new_page_responses or self._pending_downloads or self._download_tasks:
                target_page = new_page
                response = new_page_responses[-1] if new_page_responses else None

            # Fallback: Chrome's PDF viewer extension (non-headless) can
            # silently handle file URLs without firing response or download
            # events.  Detect this by probing the new page's URL and fetch
            # the file directly via the API request context.
            if target_page is page and not self._pending_downloads:
                new_url = getattr(new_page, "url", "")
                if new_url and not new_url.startswith(("about:", "chrome:")):
                    target_page = await self._probe_file_url(new_page, new_url) or page

        # Clean up response listeners on new pages
        for np, listener in _np_listeners:
            try:
                np.remove_listener("response", listener)
            except Exception:  # noqa: BLE001
                pass

        # Detect cross-domain redirects during interactions (BTI-001, etc.)
        redirect_warning = None
        try:
            initial_domain = _extract_registered_domain(initial_url)
            final_page_url = getattr(target_page, "url", initial_url)
            final_domain = _extract_registered_domain(final_page_url)
            if initial_domain and final_domain and initial_domain != final_domain:
                redirect_warning = (
                    "Cross-domain redirect detected: intended %s, "
                    "landed on %s. This may indicate session contamination "
                    "or DNS issues."
                ) % (initial_domain, final_domain)
                logger.warning(
                    "Cross-domain redirect during interaction: %s -> %s (intended: %s)",
                    initial_url, final_page_url, initial_domain,
                )
        except Exception:
            pass  # Best-effort detection

        result = await self._finalize_action(
            target_page, response=response, initial_url=initial_url,
            saw_download_response=_saw_download_response,
            redirect_warning=redirect_warning,
        )
        result.action_ms = action_ms

        # If a download was captured from a new tab, close that tab so the
        # agent returns to the original page.  Otherwise current_page() would
        # return the download tab (often about:blank) and subsequent tools
        # would fail with "Navigate to a page first."
        if result.download and target_page is not page:
            try:
                await target_page.close()
            except Exception:  # noqa: BLE001
                pass

        return result


_browser: Browser | None = None
_agent_browsers: dict[str, Browser] = {}
_agent_browser_lock = asyncio.Lock()


def _kill_driver_tree(pid: int) -> None:
    """Send SIGTERM to a Playwright driver process and its children.

    This is a synchronous, best-effort fallback used by the ``atexit`` handler
    when the async close path didn't run (e.g. the event loop was torn down).
    Killing the driver also kills the Chromium child it manages.
    """
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    except OSError:
        # Fallback: kill just the driver process if pgid failed
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def _atexit_kill_browser() -> None:
    """Last-resort cleanup: kill the Chromium/driver process tree on exit.

    Registered via ``atexit`` when a browser is created.  If the async
    ``close_browser()`` already ran, ``_browser`` is ``None`` and this is a
    no-op.  Otherwise it sends SIGTERM to the Playwright driver PID, which
    takes Chromium down with it.
    """
    if _browser is None or _browser._closed:
        return
    pid = _browser._driver_pid
    if pid is None:
        return
    logger.debug("atexit: killing browser driver tree (pid %d)", pid)
    _kill_driver_tree(pid)


async def _get_root_browser() -> Browser:
    """Return the persistent root browser, initializing it on first call."""
    global _browser
    if _browser is None:
        config = load_config()
        profile_path = Path(config.settings.home_dir) / "browser" / "profiles" / "default"
        downloads_dir = str(Path(config.virtual_computer.home_dir) / "downloads")
        headless = config.tools.browser.headless
        _browser = await Browser.start(
            str(profile_path),
            headless=headless,
            downloads_path=downloads_dir,
        )
        _browser._downloads_dir = downloads_dir
        atexit.register(_atexit_kill_browser)
    return _browser


async def get_browser() -> Browser:
    """Get the browser instance for the current agent.

    Root agents (depth 0) get the persistent singleton browser.  Sub-agents
    get an ephemeral context on the same Chrome process, seeded with the
    root's cookies and localStorage for session inheritance.
    """
    from sdk.events import get_current_agent_id, get_current_depth

    root = await _get_root_browser()
    depth = get_current_depth()

    if depth == 0:
        return root

    agent_id = get_current_agent_id() or "sub_default"
    async with _agent_browser_lock:
        if agent_id in _agent_browsers:
            return _agent_browsers[agent_id]

        state = await root._context.storage_state()
        ephemeral = await Browser.start_ephemeral(root, storage_state=state)
        _agent_browsers[agent_id] = ephemeral
        logger.info("Created ephemeral browser context for agent '%s'", agent_id)
        return ephemeral


async def release_agent_browser(agent_id: str) -> None:
    """Close and remove the ephemeral browser context for an agent."""
    async with _agent_browser_lock:
        browser = _agent_browsers.pop(agent_id, None)
    if browser is not None:
        try:
            await browser.close_context()
            logger.info("Released ephemeral browser context for agent '%s'", agent_id)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to release browser context for agent '%s'", agent_id)


async def close_browser() -> None:
    """Shutdown all browser instances — ephemeral contexts and root singleton."""
    global _browser

    # Close all ephemeral sub-agent contexts first.
    async with _agent_browser_lock:
        agents = list(_agent_browsers.items())
        _agent_browsers.clear()
    for agent_id, browser in agents:
        try:
            await browser.close_context()
        except Exception:  # noqa: BLE001
            logger.warning("Failed to close ephemeral context for '%s'", agent_id)

    if _browser is None:
        logger.debug("close_browser called but no browser instance exists")
        return
    try:
        await _browser.close()
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.warning("Suppressed exception in close_browser wrapper: %s: %s", type(exc).__name__, exc)
    except Exception as exc:  # noqa: BLE001  pragma: no cover - highly defensive
        logger.warning(
            "Suppressed unexpected exception in close_browser wrapper: %s: %s",
            type(exc).__name__,
            exc,
        )
    finally:
        _browser = None
        logger.debug("Browser singleton cleared")
