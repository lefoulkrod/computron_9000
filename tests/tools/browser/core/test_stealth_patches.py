"""Tests that stealth init scripts contain the expected patches.

These are marker tests — they verify that each critical section exists in the
script string so accidental deletions or regressions are caught early.  They
do NOT execute the JavaScript; runtime behavior is validated via live browser
testing against bot-detection sites.
"""

import inspect

import pytest

from tools.browser.core.browser import (
    ANTI_BOT_INIT_SCRIPT,
    ANTI_BOT_INIT_SCRIPT_CHROME,
    Browser,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CHROMIUM_SCRIPT = ANTI_BOT_INIT_SCRIPT
_CHROME_SCRIPT = ANTI_BOT_INIT_SCRIPT_CHROME


def _chromium_contains(needle: str) -> bool:
    return needle in _CHROMIUM_SCRIPT


def _chrome_contains(needle: str) -> bool:
    return needle in _CHROME_SCRIPT


# ---------------------------------------------------------------------------
# Webdriver patch — present in BOTH scripts (Playwright always sets it)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWebdriverPatch:
    """navigator.webdriver removal — both scripts.

    The property is deleted entirely so navigator.webdriver is undefined,
    matching a real non-automated browser.  Redefining it as false is
    detectable by fp-collect which checks for existence, not just value.
    """

    @pytest.mark.parametrize(
        "script", [_CHROMIUM_SCRIPT, _CHROME_SCRIPT], ids=["chromium", "chrome"]
    )
    def test_deletes_prototype_property(self, script):
        assert "delete Navigator.prototype.webdriver" in script

    @pytest.mark.parametrize(
        "script", [_CHROMIUM_SCRIPT, _CHROME_SCRIPT], ids=["chromium", "chrome"]
    )
    def test_deletes_instance_property(self, script):
        assert "delete navigator.webdriver" in script

    @pytest.mark.parametrize(
        "script", [_CHROMIUM_SCRIPT, _CHROME_SCRIPT], ids=["chromium", "chrome"]
    )
    def test_does_not_redefine_property(self, script):
        assert "Object.defineProperty(navigator, 'webdriver'" not in script
        assert "Object.defineProperty(Navigator.prototype, 'webdriver'" not in script


# ---------------------------------------------------------------------------
# Patches ONLY in bundled Chromium script — real Chrome handles these natively
# and patching them would replace real functions with detectable spoofs.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWindowDimensionsPatch:
    """Window dimensions — Chromium only (real Chrome's OS window manager handles this)."""

    def test_present_in_chromium(self):
        assert _chromium_contains("outerWidth")
        assert _chromium_contains("outerHeight")

    def test_absent_from_chrome_script(self):
        assert not _chrome_contains("outerWidth")
        assert not _chrome_contains("outerHeight")


@pytest.mark.unit
class TestPermissionsApiPatch:
    """Permissions API — Chromium only (headed Chrome has correct notification state)."""

    def test_returns_prompt(self):
        assert _chromium_contains("'prompt'")

    def test_uses_real_permission_status(self):
        assert _chromium_contains("geolocation")

    def test_includes_onchange(self):
        assert _chromium_contains("onchange")

    def test_absent_from_chrome_script(self):
        assert not _chrome_contains("permissions.query")


@pytest.mark.unit
class TestPluginArrayPatch:
    """PluginArray instanceof fix via Proxy — Chromium only."""

    def test_uses_proxy(self):
        assert _chromium_contains("new Proxy(_real")

    def test_has_item_method(self):
        assert _chromium_contains("function item(i)")

    def test_has_named_item_method(self):
        assert _chromium_contains("function namedItem(n)")

    def test_has_symbol_iterator(self):
        assert _chromium_contains("Symbol.iterator")

    def test_absent_from_chrome_script(self):
        assert not _chrome_contains("new Proxy(_real")


@pytest.mark.unit
class TestWebGLPatch:
    """WebGL vendor/renderer — Chromium only."""

    def test_patches_webgl1(self):
        assert _chromium_contains("_patchWebGL(WebGLRenderingContext.prototype)")

    def test_patches_webgl2(self):
        assert _chromium_contains("_patchWebGL(WebGL2RenderingContext.prototype)")

    def test_makes_native(self):
        assert _chromium_contains("_makeNative(function getParameter")

    def test_absent_from_chrome_script(self):
        assert not _chrome_contains("_patchWebGL")


@pytest.mark.unit
class TestUserAgentDataPatch:
    """userAgentData Chrome branding — Chromium only."""

    def test_adds_google_chrome_brand(self):
        assert _chromium_contains("Google Chrome")

    def test_absent_from_chrome_script(self):
        assert not _chrome_contains("Google Chrome")


@pytest.mark.unit
class TestMissingApiStubs:
    """CreepJS missing API stubs — Chromium only."""

    def test_navigator_connection(self):
        assert _chromium_contains("navigator.connection") and _chromium_contains(
            "effectiveType: '4g'"
        )

    def test_navigator_share(self):
        assert _chromium_contains("function share()")

    def test_navigator_can_share(self):
        assert _chromium_contains("function canShare()")

    def test_content_index_api(self):
        assert _chromium_contains("ServiceWorkerRegistration.prototype.index")

    def test_navigator_contacts(self):
        assert _chromium_contains("navigator.contacts") and _chromium_contains(
            "function select()"
        )

    def test_window_controls_overlay(self):
        assert _chromium_contains(
            "navigator.windowControlsOverlay"
        ) and _chromium_contains("getTitlebarAreaRect")

    def test_stubs_absent_from_chrome_script(self):
        """Real Chrome has these APIs natively — stubs must not be injected."""
        assert not _chrome_contains("effectiveType: '4g'")
        assert not _chrome_contains("ServiceWorkerRegistration.prototype.index")


# ---------------------------------------------------------------------------
# Chrome script should be minimal — only _makeNative + webdriver patch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChromeScriptMinimal:
    """The Chrome channel script should contain nothing beyond the webdriver patch."""

    def test_has_make_native_helper(self):
        assert _chrome_contains("_makeNative")

    def test_has_webdriver_patch(self):
        assert _chrome_contains("delete Navigator.prototype.webdriver")

    def test_no_languages_override(self):
        assert not _chrome_contains("navigator, 'languages'")

    def test_no_platform_override(self):
        assert not _chrome_contains("navigator, 'platform'")

    def test_no_chrome_runtime_shim(self):
        assert not _chrome_contains("window.chrome.runtime")


# ---------------------------------------------------------------------------
# Chromium args
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChromiumArgs:
    """Verify stealth-related Chromium flags are present."""

    def test_webrtc_ip_leak_prevention(self):
        """The WebRTC flag must be in Browser.start's default chromium_args."""
        source = inspect.getsource(Browser.start)
        assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in source


# ---------------------------------------------------------------------------
# Channel-aware launch configuration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChannelAwareLaunch:
    """Verify Browser.start adjusts settings based on browser channel."""

    def test_user_agent_not_forced_for_chrome_channel(self):
        """When a channel is specified, user_agent should not be in launch_kwargs."""
        source = inspect.getsource(Browser.start)
        assert "if not _use_channel" in source
        assert 'launch_kwargs["user_agent"]' in source

    def test_swiftshader_only_for_bundled_chromium(self):
        """--enable-unsafe-swiftshader is only needed for bundled Chromium."""
        source = inspect.getsource(Browser.start)
        assert "--enable-unsafe-swiftshader" in source
