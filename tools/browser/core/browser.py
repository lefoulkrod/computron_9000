"""Core Playwright browser utilities for agent tools.

This module provides a minimal, persistent Chromium context with small anti-bot tweaks
suited for LLM-powered browsing tools. It focuses on sensible defaults and clean
shutdown while keeping a light surface area.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

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

DEFAULT_UA = (
    # Keep in sync with Playwright's bundled Chromium version (currently 136)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
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

// 1) webdriver flag — real Chrome returns false (not undefined) when not automated.
// Delete the existing property first so Object.getOwnPropertyDescriptor inspections
// and prototype enumeration (as used by CreepJS) see our clean descriptor.
delete Navigator.prototype.webdriver;
const _wdGetter = _makeNative(() => false, 'get webdriver');
Object.defineProperty(Navigator.prototype, 'webdriver', {
  get: _wdGetter, configurable: true, enumerable: true,
});
// Also define on the navigator instance to cover direct instance property checks
Object.defineProperty(navigator, 'webdriver', {
  get: _wdGetter, configurable: true, enumerable: true,
});

// 2) languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// 3) platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// 4) chrome runtime object — Chromium sets window.chrome (loadTimes/csi/app) but NOT runtime.
// Real Chrome always has window.chrome.runtime (even without extensions).
window.chrome = window.chrome || {};
if (!window.chrome.runtime) {
  window.chrome.runtime = {};
}

// 5) plugins — use a Proxy wrapping the real PluginArray so instanceof checks pass.
// Object.setPrototypeOf(array, PluginArray.prototype) doesn't fool instanceof.
(function() {
  const _fakeData = [
    { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
    { name: 'Microsoft Edge PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: '' },
  ];
  const _real = navigator.plugins;  // genuine PluginArray — keeps type identity
  const _proxy = new Proxy(_real, {
    get(target, prop, receiver) {
      if (prop === 'length') return _fakeData.length;
      // Indexed access: proxy[0], proxy[1], ...
      if (typeof prop === 'string' && /^\d+$/.test(prop)) {
        return _fakeData[Number(prop)];
      }
      if (prop === 'item') return _makeNative(function item(i) { return _fakeData[i]; }, 'item');
      if (prop === 'namedItem') return _makeNative(function namedItem(n) {
        return _fakeData.find(p => p.name === n) || null;
      }, 'namedItem');
      if (prop === 'refresh') return _makeNative(function refresh() {}, 'refresh');
      if (prop === Symbol.iterator) return function* () {
        for (let i = 0; i < _fakeData.length; i++) yield _fakeData[i];
      };
      if (prop === Symbol.toStringTag) return 'PluginArray';
      return Reflect.get(target, prop, receiver);
    },
  });
  Object.defineProperty(navigator, 'plugins', { get: () => _proxy, configurable: true });
})();

// 6) WebGL vendor/renderer — patch both WebGL1 and WebGL2
(function() {
  function _patchWebGL(proto) {
    if (!proto) return;
    const _origGetParam = proto.getParameter;
    proto.getParameter = _makeNative(function getParameter(parameter) {
      if (parameter === 37445) return 'Intel Inc.';            // UNMASKED_VENDOR_WEBGL
      if (parameter === 37446) return 'Intel(R) UHD Graphics'; // UNMASKED_RENDERER_WEBGL
      return _origGetParam.call(this, parameter);
    }, 'getParameter');
  }
  _patchWebGL(WebGLRenderingContext.prototype);
  if (typeof WebGL2RenderingContext !== 'undefined') {
    _patchWebGL(WebGL2RenderingContext.prototype);
  }
})();

// 7) Permissions API — intercept notifications query but keep the function looking native
// Query a non-sensitive permission to get a real PermissionStatus object, then override
// its state to 'prompt' (the default in a fresh Chrome install).  This way instanceof
// PermissionStatus passes and the prototype chain looks genuine.
// Also override Notification.permission to match — bot.sannysoft.com catches the mismatch
// between Notification.permission ('denied' in headless) and permissionStatus.state ('prompt').
(function() {
  const _orig = window.navigator.permissions.query.bind(window.navigator.permissions);
  const _patched = _makeNative(function query(parameters) {
    if (parameters.name === 'notifications') {
      // Get a real PermissionStatus from a benign permission, then patch its state
      return _orig({ name: 'geolocation' }).then(function(status) {
        Object.defineProperty(status, 'state', { get: () => 'prompt', configurable: true });
        Object.defineProperty(status, 'onchange', { value: null, writable: true, configurable: true });
        return status;
      });
    }
    return _orig(parameters);
  }, 'query');
  Object.defineProperty(window.navigator.permissions, 'query', {
    value: _patched, writable: true, configurable: true,
  });
  // Keep Notification.permission in sync so the state/permission pair doesn't reveal spoofing
  Object.defineProperty(Notification, 'permission', {
    get: _makeNative(() => 'default', 'get permission'),
    configurable: true,
  });
})();

// 8) outerWidth/outerHeight — must not exceed screen dimensions
// (Playwright's maximized window can exceed the emulated screen size, which is impossible in a real browser)
Object.defineProperty(window, 'outerWidth',  { get: () => screen.width,        configurable: true });
Object.defineProperty(window, 'outerHeight', { get: () => screen.height + 74,  configurable: true });

// 9) userAgentData — add "Google Chrome" brand (Playwright only exposes "Chromium")
(function() {
  const _uad = navigator.userAgentData;
  if (!_uad) return;
  const ver = (_uad.brands.find(b => b.brand === 'Chromium') || {}).version || '136';
  const brands = [
    { brand: 'Not.A/Brand', version: '99' },
    { brand: 'Chromium',    version: ver },
    { brand: 'Google Chrome', version: ver },
  ];
  Object.defineProperty(navigator, 'userAgentData', {
    get: () => new Proxy(_uad, {
      get(t, prop) {
        if (prop === 'brands') return brands;
        const val = t[prop];
        return typeof val === 'function' ? val.bind(t) : val;
      }
    }),
    configurable: true
  });
})();

// 10) Missing API stubs — CreepJS flags these as absent in headless/automation environments
(function() {
  // a) navigator.connection (Network Information API)
  if (!navigator.connection) {
    const _conn = {
      downlink: 10, downlinkMax: Infinity, effectiveType: '4g',
      rtt: 50, saveData: false, type: 'wifi',
      addEventListener: _makeNative(function addEventListener() {}, 'addEventListener'),
      removeEventListener: _makeNative(function removeEventListener() {}, 'removeEventListener'),
    };
    Object.defineProperty(navigator, 'connection', {
      get: _makeNative(function connection() { return _conn; }, 'get connection'),
      configurable: true, enumerable: true,
    });
  }

  // b) navigator.share() / navigator.canShare() (Web Share API)
  if (!navigator.share) {
    Object.defineProperty(navigator, 'share', {
      value: _makeNative(function share() {
        return Promise.reject(new DOMException('Share canceled', 'AbortError'));
      }, 'share'),
      writable: true, configurable: true,
    });
  }
  if (!navigator.canShare) {
    Object.defineProperty(navigator, 'canShare', {
      value: _makeNative(function canShare() { return false; }, 'canShare'),
      writable: true, configurable: true,
    });
  }

  // c) Content Index API on ServiceWorkerRegistration
  if (typeof ServiceWorkerRegistration !== 'undefined' && !ServiceWorkerRegistration.prototype.index) {
    ServiceWorkerRegistration.prototype.index = {
      add: _makeNative(function add() { return Promise.resolve(); }, 'add'),
      delete: _makeNative(function delete_() { return Promise.resolve(); }, 'delete'),
      getAll: _makeNative(function getAll() { return Promise.resolve([]); }, 'getAll'),
    };
  }

  // d) navigator.contacts (Contact Picker API)
  if (!navigator.contacts) {
    const _contacts = {
      select: _makeNative(function select() {
        return Promise.reject(new DOMException('Contact picker unavailable', 'InvalidStateError'));
      }, 'select'),
      getProperties: _makeNative(function getProperties() {
        return Promise.resolve(['email', 'name', 'tel']);
      }, 'getProperties'),
    };
    Object.defineProperty(navigator, 'contacts', {
      get: _makeNative(function contacts() { return _contacts; }, 'get contacts'),
      configurable: true, enumerable: true,
    });
  }

  // e) navigator.windowControlsOverlay (Window Controls Overlay API — "noTaskbar" flag)
  if (!navigator.windowControlsOverlay) {
    const _wco = {
      visible: false,
      getTitlebarAreaRect: _makeNative(function getTitlebarAreaRect() {
        return new DOMRect(0, 0, 0, 0);
      }, 'getTitlebarAreaRect'),
      addEventListener: _makeNative(function addEventListener() {}, 'addEventListener'),
      removeEventListener: _makeNative(function removeEventListener() {}, 'removeEventListener'),
    };
    Object.defineProperty(navigator, 'windowControlsOverlay', {
      get: _makeNative(function windowControlsOverlay() { return _wco; }, 'get windowControlsOverlay'),
      configurable: true, enumerable: true,
    });
  }
})();
"""

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

PAGE_CHANGE_DETECTION_SCRIPT = r"""
window.__page_change__ = { nav: false, dom: false, hard: false, spa: false };

(function () {
  // Define the read/reset API first so perform_interaction can always
  // access them, even if the DOM observers below fail to attach
  // (e.g. when addInitScript runs before document.documentElement exists).
  window.__resetPageChange = () => {
    window.__page_change__ = { nav: false, dom: false, hard: false, spa: false };
  };
  window.__getPageChange = () => window.__page_change__;

  window.addEventListener("beforeunload", () => {
    window.__page_change__.nav = true;
    window.__page_change__.hard = true;
  });

  const push = history.pushState;
  history.pushState = function () {
    window.__page_change__.nav = true;
    window.__page_change__.spa = true;
    return push.apply(this, arguments);
  };

  const replace = history.replaceState;
  history.replaceState = function () {
    window.__page_change__.nav = true;
    window.__page_change__.spa = true;
    return replace.apply(this, arguments);
  };

  window.addEventListener("popstate", () => {
    window.__page_change__.nav = true;
    window.__page_change__.spa = true;
  });

  const markChange = () => {
    window.__page_change__.dom = true;
  };
  window.addEventListener("input", markChange, true);
  window.addEventListener("change", markChange, true);

  // DOM observers need document.documentElement which may not exist yet
  // when addInitScript runs early.  Defer attachment if necessary.
  function _attachDomObservers() {
    const root = document.documentElement || document.body;
    if (!root) return;

    new MutationObserver((mutations) => {
      const significantMutation = mutations.some(m => {
        if (m.type === 'attributes' && m.attributeName === 'value') {
          const target = m.target;
          if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
            return false;
          }
        }
        if (m.type === 'characterData') {
          let node = m.target.parentNode;
          while (node) {
            if (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') {
              return false;
            }
            node = node.parentNode;
          }
        }
        return true;
      });
      if (significantMutation) {
        window.__page_change__.dom = true;
      }
    }).observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      characterData: true
    });

    try {
      new ResizeObserver(() => {
        window.__page_change__.dom = true;
      }).observe(root);
    } catch (err) {
      window.addEventListener("resize", markChange);
    }
  }

  // Attach immediately if the document root exists, otherwise wait.
  if (document.documentElement) {
    _attachDomObservers();
  } else {
    document.addEventListener("DOMContentLoaded", _attachDomObservers, { once: true });
  }
})();
"""


Reason = Literal["browser-navigation", "history-navigation", "dom-mutation", "no-change"]


class BrowserInteractionResult(BaseModel):
    """Structured metadata describing the outcome of a browser interaction."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    navigation: bool
    page_changed: bool
    reason: Reason
    navigation_response: Response | None = None
    download: DownloadInfo | None = None


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
        self._active_frame: Frame | None = None
        self._pending_downloads: list[DownloadInfo] = []
        self._downloads_dir: str = ""
        self._container_dir: str = ""
        self._download_listener_pages: set[int] = set()  # page id() tracking
        self._download_tasks: set[asyncio.Task[None]] = set()

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

    async def _handle_download(self, download: Any) -> None:
        """Process a Playwright download event and record the result."""
        try:
            path = await download.path()
            if not path:
                logger.warning("Download completed but no path available")
                return

            from tools.browser.core._file_detection import build_download_info_from_path

            info = build_download_info_from_path(
                host_path=path,
                container_dir=self._container_dir,
            )
            self._pending_downloads.append(info)
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

    @staticmethod
    def _cleanup_stale_profile_locks(profile_path: Path) -> None:
        """Remove stale Chromium lock files left by a previous unclean shutdown.

        Chromium creates ``SingletonLock``, ``SingletonCookie``, and
        ``SingletonSocket`` symlinks inside the user-data directory.
        ``SingletonLock`` points to ``<hostname>-<pid>``.  If that PID is no
        longer running we can safely remove all three files so that a fresh
        browser can start.
        """
        lock = profile_path / "SingletonLock"
        if not lock.is_symlink() and not lock.exists():
            return

        try:
            target = os.readlink(lock)
        except OSError:
            return

        # Format is "<hostname>-<pid>"
        parts = target.rsplit("-", 1)
        if len(parts) == 2:
            try:
                pid = int(parts[1])
            except ValueError:
                pid = None

            if pid is not None:
                try:
                    # Signal 0 checks existence without actually signalling.
                    os.kill(pid, 0)
                    # Process is alive — don't touch the locks.
                    return
                except ProcessLookupError:
                    pass  # PID is dead — stale lock, clean up below.
                except PermissionError:
                    # Process exists but we can't signal it — leave locks alone.
                    return

        # Remove stale lock files.
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            target_path = profile_path / name
            try:
                target_path.unlink(missing_ok=True)
                logger.info("Removed stale browser lock file: %s", target_path)
            except OSError as exc:
                logger.warning("Could not remove stale lock %s: %s", target_path, exc)

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
        downloads_path: str | None = None,
        geolocation: Geolocation | None = None,  # {"latitude": 37.7749, "longitude": -122.4194}
        permissions: list[str] | None = None,  # e.g. ["geolocation", "clipboard-read", "clipboard-write"]
        extra_headers: dict[str, str] | None = None,  # sent with every request
        args: list[str] | None = None,  # extra Chromium args
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
            downloads_path: Directory where downloaded files are saved. Defaults to a
                system temp directory if not provided.
            geolocation: Optional geolocation to emulate.
            permissions: Optional list of permissions to grant to all pages.
            extra_headers: Additional default HTTP headers for all requests.
            args: Additional Chromium command-line flags.

        Returns:
            A ready-to-use ``Browser`` wrapping the persistent context.
        """
        profile_path = Path(profile_dir).expanduser().resolve()
        profile_path.mkdir(parents=True, exist_ok=True)

        # Remove stale lock files left by previous unclean shutdowns so
        # Chromium can start even after a hard kill.
        cls._cleanup_stale_profile_locks(profile_path)

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
            # Enable software WebGL fallback so sites don't detect missing GPU acceleration
            "--enable-unsafe-swiftshader",
            # Prevent IP leak via RTCPeerConnection without fully disabling WebRTC
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            # Disable the built-in PDF/media viewer so files trigger download
            # events instead of loading in an inline viewer.  The download
            # listener captures real file bytes automatically.
            "--disable-pdf-viewer",
        ]
        if args:
            chromium_args.extend(args)

        # Resolve and create downloads directory if specified
        resolved_downloads_path: str | None = None
        if downloads_path:
            dl_path = Path(downloads_path).expanduser().resolve()
            dl_path.mkdir(parents=True, exist_ok=True)
            resolved_downloads_path = str(dl_path)

        launch_kwargs: dict[str, Any] = dict(
            user_data_dir=str(profile_path),
            headless=headless,
            proxy=proxy,
            args=chromium_args,
            viewport=_viewport(),
            user_agent=user_agent,
            locale=locale,
            timezone_id=timezone_id,
            accept_downloads=accept_downloads,
            downloads_path=resolved_downloads_path,
            geolocation=geolocation,
            permissions=permissions or [],
            java_script_enabled=True,  # ensure JS is enabled
        )

        pw: Playwright = await async_playwright().start()
        try:
            context = await pw.chromium.launch_persistent_context(**launch_kwargs)
        except Exception:
            # If launch fails (e.g. stale lock that appeared between cleanup
            # and launch), stop the driver to kill any orphaned Chromium child,
            # re-clean locks, and retry once with a fresh driver.
            try:
                await asyncio.wait_for(pw.stop(), timeout=5.0)
            except Exception:  # noqa: BLE001
                pass
            cls._cleanup_stale_profile_locks(profile_path)
            pw = await async_playwright().start()
            context = await pw.chromium.launch_persistent_context(**launch_kwargs)

        # HTTP headers to look like a normal browser.
        # IMPORTANT: Do NOT include Sec-Fetch-* headers here. Playwright/Chromium sets
        # those correctly per request type (navigate vs script vs image etc.). Forcing
        # them globally breaks subresource loading on CDNs that validate the headers.
        headers = {
            "Accept-Language": f"{locale},en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",  # 👈 important for GitHub
            **(extra_headers or {}),
        }
        await context.set_extra_http_headers(headers)

        # Anti-bot JS shims
        await context.add_init_script(ANTI_BOT_INIT_SCRIPT)
        await context.add_init_script(_OPEN_SHADOW_DOM_SCRIPT)
        await context.add_init_script(PAGE_CHANGE_DETECTION_SCRIPT)

        return cls(context=context, extra_headers=headers, pw=pw)

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

            # Verify the frame's content is accessible (not cross-origin blocked)
            try:
                child_count = await frame.evaluate(
                    "() => document.body ? document.body.children.length : 0"
                )
                if child_count and area > best_area:
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

    async def navigate(self, url: str) -> BrowserInteractionResult:
        """Navigate to *url* and return a ``BrowserInteractionResult``.

        Handles page creation, frame clearing, settling, iframe detection,
        and file download detection so callers get a unified result.
        """
        from tools.browser.core._file_detection import (
            is_file_content_type,
            save_response_as_file,
        )

        try:
            page = await self.current_page()
        except RuntimeError:
            page = await self.new_page()
        self.clear_active_frame()
        # Clear any pending downloads before navigation
        self._pending_downloads.clear()
        response = await page.goto(url, wait_until="domcontentloaded")

        # --- File download detection ---
        # With --disable-pdf-viewer, PDFs trigger a download event instead
        # of loading inline.  Wait for any pending download tasks, then
        # check the download listener first (real file bytes).  Fall back
        # to response.body() for servers that stream the file inline.
        download_info: DownloadInfo | None = None

        # Wait for download tasks that may still be completing
        if self._download_tasks:
            await asyncio.gather(*self._download_tasks, return_exceptions=True)

        # Prefer download event (has real bytes from disk)
        downloads = self.drain_downloads()
        if downloads:
            download_info = downloads[0]
        elif response is not None:
            ct = response.headers.get("content-type", "")
            if is_file_content_type(ct):
                try:
                    download_info = await save_response_as_file(
                        response,
                        downloads_dir=self._downloads_dir or ".",
                        container_dir=self._container_dir or "/tmp",
                    )
                except Exception:
                    logger.exception("Failed to save file from navigation to %s", url)

        if download_info is None:
            # Normal page — settle and detect iframes
            wait_cfg = load_config().tools.browser.waits
            await browser_waits.wait_for_page_settle(page, waits=wait_cfg)

        return BrowserInteractionResult(
            navigation=True,
            page_changed=True,
            reason="browser-navigation",
            navigation_response=response,
            download=download_info,
        )

    async def navigate_back(self) -> BrowserInteractionResult:
        """Navigate back in history via ``perform_interaction``."""
        page = await self.current_page()

        async def _back() -> None:
            await page.go_back(wait_until="domcontentloaded")

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

    async def perform_interaction(
        self,
        action: Callable[[], Awaitable[Any]],
    ) -> BrowserInteractionResult:
        """Perform an interaction while tracking navigation and DOM changes."""
        page = await self.current_page()
        wait_cfg = load_config().tools.browser.waits
        initial_url = getattr(page, "url", "")

        try:
            await page.evaluate("window.__resetPageChange && window.__resetPageChange()")
        except PlaywrightError as exc:
            logger.debug("Failed to reset page change markers on %s: %s", initial_url or "<unknown>", exc)
        except Exception as exc:  # noqa: BLE001 - best-effort guard
            logger.debug("Unexpected error resetting page change markers on %s: %s", initial_url or "<unknown>", exc)

        # Clear downloads and capture main-frame responses during the action
        self._pending_downloads.clear()
        captured_responses: list[Response] = []

        def _on_response(resp: Response) -> None:
            # Only capture main-frame navigations (not sub-resources)
            if resp.frame == page.main_frame:
                captured_responses.append(resp)

        page.on("response", _on_response)

        await action()

        # Drain any in-flight progressive screenshot so it doesn't race with
        # the post-action page.evaluate calls below (both share the CDP
        # connection).  This is the single chokepoint for all interactions,
        # so individual callers never need to flush manually.
        from tools.browser.events import flush_progressive_screenshot

        await flush_progressive_screenshot()

        def _extract_flags(state: dict[str, object], *, current_url: str, initial_url: str) -> tuple[bool, bool, bool]:
            hard = bool(state.get("hard"))
            spa = bool(state.get("spa"))
            dom = bool(state.get("dom"))
            if not (hard or spa) and initial_url and current_url and current_url != initial_url:
                hard = True
            return hard, spa, dom

        change_state: dict[str, object] = {}
        try:
            result = await page.evaluate("window.__getPageChange && window.__getPageChange()")
        except PlaywrightError as exc:
            logger.debug("Failed to read page change markers on %s: %s", initial_url or "<unknown>", exc)
        except Exception as exc:  # noqa: BLE001 - best-effort guard
            logger.debug("Unexpected error reading page change markers on %s: %s", initial_url or "<unknown>", exc)
        else:
            if isinstance(result, dict):
                change_state = result
                logger.debug("Initial change_state after action: %s", change_state)

        current_url = getattr(page, "url", initial_url)
        hard_nav, spa_nav, dom_change = _extract_flags(change_state, current_url=current_url, initial_url=initial_url)

        navigation_detected = hard_nav or spa_nav
        if navigation_detected:
            reason_value: Reason = "browser-navigation" if hard_nav else "history-navigation"
        elif dom_change:
            reason_value = "dom-mutation"
        else:
            reason_value = "no-change"

        page_changed = navigation_detected or dom_change

        try:
            await browser_waits.wait_for_page_settle(page, waits=wait_cfg)
        except Exception as exc:  # noqa: BLE001 - wait helper already logs Playwright errors
            logger.debug("Page settle helper raised unexpectedly: %s", exc)
        else:
            # Re-read change markers after settling in case asynchronous updates occurred.
            try:
                post_state = await page.evaluate("window.__getPageChange && window.__getPageChange()")
            except PlaywrightError as exc:
                logger.debug(
                    "Failed to read post-settle page change markers on %s: %s",
                    getattr(page, "url", "<unknown>") or "<unknown>",
                    exc,
                )
            except Exception as exc:  # noqa: BLE001 - best-effort guard
                logger.debug(
                    "Unexpected error reading post-settle change markers on %s: %s",
                    getattr(page, "url", "<unknown>") or "<unknown>",
                    exc,
                )
            else:
                if isinstance(post_state, dict):
                    logger.debug("Post-settle change_state: %s", post_state)
                    for key in ("hard", "spa", "dom"):
                        if post_state.get(key):
                            change_state[key] = True
                    logger.debug("Merged change_state after post-settle: %s", change_state)

        final_url = getattr(page, "url", current_url)
        hard_nav, spa_nav, dom_change = _extract_flags(change_state, current_url=final_url, initial_url=initial_url)
        navigation_detected = hard_nav or spa_nav
        if navigation_detected:
            reason_value = "browser-navigation" if hard_nav else "history-navigation"
        elif dom_change:
            reason_value = "dom-mutation"
        else:
            reason_value = "no-change"

        page_changed = navigation_detected or dom_change

        # Remove the temporary response listener
        page.remove_listener("response", _on_response)

        # Detect file downloads from the interaction
        download_info: DownloadInfo | None = None

        # Wait briefly for any in-flight download events to complete
        if self._download_tasks:
            await asyncio.gather(*self._download_tasks, return_exceptions=True)

        # Case 1: Playwright download event (Content-Disposition: attachment)
        pending = self.drain_downloads()
        if pending:
            download_info = pending[0]  # Use the first download

        # Case 2: Navigation to an inline file (PDF viewer, image)
        if download_info is None and captured_responses:
            from tools.browser.core._file_detection import (
                is_file_content_type,
                save_response_as_file,
            )

            # Check the last main-frame response (final redirect target)
            last_response = captured_responses[-1]
            ct = last_response.headers.get("content-type", "")
            if is_file_content_type(ct):
                try:
                    download_info = await save_response_as_file(
                        last_response,
                        downloads_dir=self._downloads_dir or ".",
                        container_dir=self._container_dir or "/tmp",
                    )
                except Exception:
                    logger.exception("Failed to save file from interaction response")

        metadata = BrowserInteractionResult(
            navigation=navigation_detected,
            page_changed=page_changed,
            reason=reason_value,
            navigation_response=None,
            download=download_info,
        )

        logger.debug(
            "Browser.perform_interaction completed for %s | navigation=%s reason=%s dom_change=%s",
            current_url or "<unknown>",
            navigation_detected,
            reason_value,
            dom_change,
        )

        # Detect dominant iframe after the interaction settles.
        # Navigation clears any previously tracked frame (new page = fresh state).
        if navigation_detected:
            self._active_frame = None
        else:
            try:
                previous_frame = self._active_frame
                dominant = await self._detect_dominant_frame(page)
                if dominant != self._active_frame:
                    if dominant is not None:
                        logger.debug("Dominant iframe detected; shifting tools to frame %s", dominant.url)
                    elif self._active_frame is not None:
                        logger.debug("Dominant iframe no longer present; returning to main page")
                    self._active_frame = dominant

                # When a NEW dominant iframe appears (e.g. a booking widget),
                # wait for its content to load.  SPA iframes insert quickly
                # into the DOM but their JS frameworks need time to render.
                # Use "load" (not "domcontentloaded") so scripts finish
                # executing before we snapshot — otherwise we'd capture the
                # noscript fallback instead of the rendered SPA content.
                if dominant is not None and dominant != previous_frame:
                    try:
                        await dominant.wait_for_load_state("load", timeout=5000)
                        await browser_waits.wait_for_page_settle(
                            dominant, waits=wait_cfg,
                        )
                    except (PlaywrightTimeoutError, PlaywrightError):
                        pass  # Best effort — some iframes may be slow
            except Exception:  # noqa: BLE001 - detection is best-effort
                logger.debug("Dominant frame detection failed; keeping current state")

        # Add human-like delay after page changes (looks like user is reading/processing)
        if page_changed:
            delay_ms = random.randint(300, 800)
            logger.debug("Adding %dms post-page-change delay to mimic human reading", delay_ms)
            await asyncio.sleep(delay_ms / 1000.0)

        return metadata


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
        # Route browser downloads to the virtual computer's shared home directory
        # so the agent can access downloaded files via run_bash_cmd.
        downloads_path = config.virtual_computer.home_dir
        _browser = await Browser.start(str(profile_path), downloads_path=downloads_path)
        _browser._downloads_dir = downloads_path
        _browser._container_dir = config.virtual_computer.container_working_dir
    return _browser


async def close_browser() -> None:
    """Shutdown the persistent browser instance if it exists.

    This function closes the browser context and resets the singleton instance.

    Returns:
        None
    """
    global _browser
    if _browser is None:
        logger.debug("close_browser called but no browser instance exists")
        return
    try:
        await _browser.close()
    except PlaywrightError as exc:  # pragma: no cover - defensive
        # Should generally be handled inside Browser.close already, but we add
        # an outer guard in case of future changes.
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
