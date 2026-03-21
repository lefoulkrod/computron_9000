"""Core Playwright browser utilities for agent tools.

This module provides a minimal, persistent Chromium context with small anti-bot tweaks
suited for LLM-powered browsing tools. It focuses on sensible defaults and clean
shutdown while keeping a light surface area.
"""

from __future__ import annotations

import atexit
import asyncio
import time
import json
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
    # Keep in sync with Playwright's bundled Chromium version (currently 136).
    # Only used when launching bundled Chromium (channel=None).  When a real
    # Chrome channel is specified the browser's native UA is kept as-is so
    # that the User-Agent string and Sec-CH-UA client-hint headers stay in sync.
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
# The only patch needed for real Chrome: Playwright forces
# navigator.webdriver = true via CDP regardless of browser channel.
# ---------------------------------------------------------------------------

_CHROME_CHANNEL_PATCHES_JS = r"""
// webdriver flag — real Chrome returns false (not undefined) when not automated.
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
"""

# ---------------------------------------------------------------------------
# Full patch set for bundled Chromium (channel=None).
# Bundled Chromium is missing native Chrome properties (plugins, brands,
# chrome.runtime, etc.) and needs window/permissions fixes that headed
# real Chrome handles correctly on its own.
# ---------------------------------------------------------------------------

_CHROMIUM_ONLY_PATCHES_JS = r"""
// 1) webdriver flag — same as Chrome channel patch above
delete Navigator.prototype.webdriver;
const _wdGetter = _makeNative(() => false, 'get webdriver');
Object.defineProperty(Navigator.prototype, 'webdriver', {
  get: _wdGetter, configurable: true, enumerable: true,
});
Object.defineProperty(navigator, 'webdriver', {
  get: _wdGetter, configurable: true, enumerable: true,
});

// 2) outerWidth/outerHeight — must not exceed screen dimensions
// (Playwright's maximized window can exceed the emulated screen size, which is impossible in a real browser)
Object.defineProperty(window, 'outerWidth',  { get: () => screen.width,        configurable: true });
Object.defineProperty(window, 'outerHeight', { get: () => screen.height + 74,  configurable: true });

// 3) Permissions API — intercept notifications query but keep the function looking native
// Query a non-sensitive permission to get a real PermissionStatus object, then override
// its state to 'prompt' (the default in a fresh Chrome install).  This way instanceof
// PermissionStatus passes and the prototype chain looks genuine.
// Also override Notification.permission to match — bot.sannysoft.com catches the mismatch
// between Notification.permission ('denied' in headless) and permissionStatus.state ('prompt').
(function() {
  const _orig = window.navigator.permissions.query.bind(window.navigator.permissions);
  const _patched = _makeNative(function query(parameters) {
    if (parameters.name === 'notifications') {
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
  Object.defineProperty(Notification, 'permission', {
    get: _makeNative(() => 'default', 'get permission'),
    configurable: true,
  });
})();

// 4) languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// 5) platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// 6) chrome runtime object — Chromium sets window.chrome (loadTimes/csi/app) but NOT runtime.
// Real Chrome always has window.chrome.runtime (even without extensions).
window.chrome = window.chrome || {};
if (!window.chrome.runtime) {
  window.chrome.runtime = {};
}

// 7) plugins — use a Proxy wrapping the real PluginArray so instanceof checks pass.
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

// 8) WebGL vendor/renderer — patch both WebGL1 and WebGL2
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


def _build_anti_bot_script(*, use_channel: bool) -> str:
    """Assemble the anti-bot init script for the given browser mode.

    Args:
        use_channel: True when launching a real Chrome channel (``"chrome"``),
            False for bundled Chromium.  Real Chrome only needs the webdriver
            patch — everything else (plugins, brands, permissions, window
            dimensions, missing APIs) is already correct natively and patching
            it would replace real functions with spoofed ones that are
            themselves detectable.
    """
    parts = ["// --- Stealth patches to reduce automation detection ---"]
    parts.append(_MAKE_NATIVE_JS)
    if use_channel:
        parts.append(_CHROME_CHANNEL_PATCHES_JS)
    else:
        parts.append(_CHROMIUM_ONLY_PATCHES_JS)
    return "\n".join(parts)


# Pre-built scripts for import convenience (e.g. tests).
# ANTI_BOT_INIT_SCRIPT is the full Chromium script for backward compatibility.
ANTI_BOT_INIT_SCRIPT = _build_anti_bot_script(use_channel=False)
ANTI_BOT_INIT_SCRIPT_CHROME = _build_anti_bot_script(use_channel=True)

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
        use_channel: bool = False,
    ) -> None:
        """Initialize the browser wrapper.

        Args:
            context: The persistent Playwright browser context.
            extra_headers: Default HTTP headers applied to all requests.
            pw: The Playwright driver instance used to launch the context.
            use_channel: True when using a real Chrome channel. Disables
                viewport overrides so the OS window manager controls sizing.
        """
        self._context: BrowserContext = context
        self._extra_headers: dict[str, str] = extra_headers or {}
        self._pw: Playwright | None = pw
        self._use_channel: bool = use_channel
        self._closed: bool = False
        self._active_frame: Frame | None = None
        self._pending_downloads: list[DownloadInfo] = []
        self._downloads_dir: str = ""
        self._container_dir: str = ""
        self._download_listener_pages: set[int] = set()  # page id() tracking
        self._download_tasks: set[asyncio.Task[None]] = set()

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

    @staticmethod
    def _mark_profile_clean_exit(profile_path: Path) -> None:
        """Patch the Chromium ``Preferences`` file so the next launch won't
        show the "Restore pages?" / "Chrome didn't shut down correctly" bubble.

        Chrome checks ``profile.exit_type``; if it's ``"Crashed"`` or missing
        it shows the restore prompt.  Writing ``"Normal"`` before launch
        prevents that.
        """
        prefs_file = profile_path / "Default" / "Preferences"
        if not prefs_file.exists():
            return
        try:
            prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
            profile_section = prefs.setdefault("profile", {})
            if profile_section.get("exit_type") != "Normal":
                profile_section["exit_type"] = "Normal"
                profile_section["exited_cleanly"] = True
                prefs_file.write_text(
                    json.dumps(prefs, separators=(",", ":")),
                    encoding="utf-8",
                )
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Could not patch profile exit_type: %s", exc)

    @classmethod
    async def start(
        cls,
        profile_dir: str,
        *,
        channel: str | None = None,
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
            channel: Browser channel (``"chrome"`` for system Chrome, ``None``
                for bundled Chromium).
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

        # Mark the profile as cleanly exited so Chrome doesn't show the
        # "Restore pages?" bubble on next launch.
        cls._mark_profile_clean_exit(profile_path)

        _use_channel = channel is not None

        # -----------------------------------------------------------------
        # Chromium args — real Chrome needs fewer overrides since it already
        # has correct TLS fingerprint, client hints, and native APIs.
        # -----------------------------------------------------------------
        # Shared args: always needed regardless of channel
        chromium_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=AutomationControlled",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            *(["--start-maximized"] if not headless else []),
            # Suppress the "Chrome is being controlled by automated test software"
            # infobar.  --disable-infobars is deprecated; the banner is triggered by
            # Playwright's implicit --enable-automation flag, so we must explicitly
            # opt out plus suppress the "crashed" bubble on unclean shutdown.
            "--enable-automation=false",
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
            # Prevent IP leak via RTCPeerConnection without fully disabling WebRTC
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            # Disable the built-in PDF/media viewer so files trigger download
            # events instead of loading in an inline viewer.  The download
            # listener captures real file bytes automatically.
            "--disable-pdf-viewer",
        ]
        if not _use_channel:
            # Bundled Chromium needs extra help to look like a real browser
            chromium_args.extend([
                "--disable-features=IsolateOrigins,site-per-process",
                "--enable-features=NetworkService,NetworkServiceInProcess",
                "--ignore-certificate-errors",
                # Software WebGL fallback so sites don't detect missing GPU
                "--enable-unsafe-swiftshader",
            ])
        if args:
            chromium_args.extend(args)

        # Resolve and create downloads directory if specified
        resolved_downloads_path: str | None = None
        if downloads_path:
            dl_path = Path(downloads_path).expanduser().resolve()
            dl_path.mkdir(parents=True, exist_ok=True)
            resolved_downloads_path = str(dl_path)

        # Both real Chrome and bundled Chromium get an explicit viewport.
        # --start-maximized is unreliable on some Linux window managers,
        # leading to odd window dimensions.  The jitter keeps runs from
        # being pixel-identical.
        viewport = _viewport()

        launch_kwargs: dict[str, Any] = dict(
            user_data_dir=str(profile_path),
            channel=channel,
            headless=headless,
            proxy=proxy,
            args=chromium_args,
            viewport=viewport,
            locale=locale,
            timezone_id=timezone_id,
            accept_downloads=accept_downloads,
            downloads_path=resolved_downloads_path,
            geolocation=geolocation,
            permissions=permissions or [],
            java_script_enabled=True,  # ensure JS is enabled
        )
        # Only override the UA for bundled Chromium.  Real Chrome already
        # sends a correct User-Agent that matches its Sec-CH-UA client-hint
        # headers; overriding it creates a detectable mismatch.
        if not _use_channel:
            launch_kwargs["user_agent"] = user_agent

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
            **(extra_headers or {}),
        }
        if not _use_channel:
            # Real Chrome sets Accept-Encoding natively; only force it for
            # bundled Chromium where GitHub needs explicit br support.
            headers["Accept-Encoding"] = "gzip, deflate, br"
        await context.set_extra_http_headers(headers)

        # Anti-bot JS shims — channel-aware to avoid conflicts with real
        # Chrome's native properties (plugins, userAgentData, etc.)
        anti_bot = _build_anti_bot_script(use_channel=_use_channel)
        await context.add_init_script(anti_bot)
        await context.add_init_script(_OPEN_SHADOW_DOM_SCRIPT)

        return cls(context=context, extra_headers=headers, pw=pw, use_channel=_use_channel)

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

    async def navigate(self, url: str) -> BrowserInteractionResult:
        """Navigate to *url* and return a ``BrowserInteractionResult``."""
        try:
            page = await self.current_page()
        except RuntimeError:
            page = await self.new_page()
        self.clear_active_frame()
        self._pending_downloads.clear()
        initial_url = getattr(page, "url", "")
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
        return await self._finalize_action(page, response=response, initial_url=initial_url)

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

    async def _finalize_action(
        self,
        page: Page,
        *,
        response: Response | None,
        initial_url: str,
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
                        container_dir=self._container_dir or "/tmp",
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

        # 3. Iframe detection
        frame_transition: str | None = None
        final_url = getattr(page, "url", initial_url)
        navigated = bool(initial_url and final_url and final_url != initial_url)

        if navigated:
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
                    container_dir=self._container_dir or "/tmp",
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
        captured_responses: list[Response] = []

        # Track pages opened during this interaction (popups / target=_blank)
        # and capture their document responses so file downloads in new tabs
        # are detected properly.
        new_pages: list[Page] = []
        new_page_responses: list[Response] = []
        _np_listeners: list[tuple[Page, Callable[..., Any]]] = []

        def _on_response(resp: Response) -> None:
            if resp.frame == page.main_frame and resp.request.resource_type == "document":
                captured_responses.append(resp)

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

        result = await self._finalize_action(
            target_page, response=response, initial_url=initial_url,
        )
        result.action_ms = action_ms
        return result


_browser: Browser | None = None


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
        channel = config.tools.browser.channel
        headless = config.tools.browser.headless
        _browser = await Browser.start(str(profile_path), channel=channel, headless=headless, downloads_path=downloads_path)
        _browser._downloads_dir = downloads_path
        _browser._container_dir = config.virtual_computer.container_working_dir
        atexit.register(_atexit_kill_browser)
    return _browser


async def close_browser() -> None:
    """Shutdown the persistent browser instance if it exists.

    This function closes the browser context and resets the singleton instance.
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
