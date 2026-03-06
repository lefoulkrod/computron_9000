"""Tests that ANTI_BOT_INIT_SCRIPT contains the expected stealth patches.

These are marker tests — they verify that each critical section exists in the
script string so accidental deletions or regressions are caught early.  They
do NOT execute the JavaScript; runtime behavior is validated via live browser
testing against bot-detection sites.
"""

import pytest

from tools.browser.core.browser import ANTI_BOT_INIT_SCRIPT, Browser

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCRIPT = ANTI_BOT_INIT_SCRIPT


def _contains(needle: str) -> bool:
    return needle in _SCRIPT


# ---------------------------------------------------------------------------
# Patch existence markers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWebdriverPatch:
    """Patch #1 — navigator.webdriver deep detection defeat."""

    def test_deletes_prototype_property(self):
        assert _contains("delete Navigator.prototype.webdriver")

    def test_returns_false_not_undefined(self):
        assert _contains("() => false")

    def test_defines_on_navigator_instance(self):
        assert _contains("Object.defineProperty(navigator, 'webdriver'")


@pytest.mark.unit
class TestPluginArrayPatch:
    """Patch #5 — PluginArray instanceof fix via Proxy."""

    def test_uses_proxy(self):
        assert _contains("new Proxy(_real")

    def test_has_item_method(self):
        assert _contains("function item(i)")

    def test_has_named_item_method(self):
        assert _contains("function namedItem(n)")

    def test_has_symbol_iterator(self):
        assert _contains("Symbol.iterator")


@pytest.mark.unit
class TestWebGLPatch:
    """Patch #6 — WebGL vendor/renderer for both WebGL1 and WebGL2."""

    def test_patches_webgl1(self):
        assert _contains("_patchWebGL(WebGLRenderingContext.prototype)")

    def test_patches_webgl2(self):
        assert _contains("_patchWebGL(WebGL2RenderingContext.prototype)")

    def test_makes_native(self):
        # The patched getParameter should be wrapped with _makeNative
        assert _contains("_makeNative(function getParameter")


@pytest.mark.unit
class TestPermissionsApiPatch:
    """Patch #7 — Permissions API returns 'prompt' via real PermissionStatus."""

    def test_returns_prompt(self):
        assert _contains("'prompt'")

    def test_uses_real_permission_status(self):
        # Must query a real permission to get a genuine PermissionStatus object
        assert _contains("geolocation")

    def test_includes_onchange(self):
        assert _contains("onchange")


@pytest.mark.unit
class TestMissingApiStubs:
    """Patch #10 — CreepJS missing API stubs."""

    def test_navigator_connection(self):
        assert _contains("navigator.connection") and _contains("effectiveType: '4g'")

    def test_navigator_share(self):
        assert _contains("function share()")

    def test_navigator_can_share(self):
        assert _contains("function canShare()")

    def test_content_index_api(self):
        assert _contains("ServiceWorkerRegistration.prototype.index")

    def test_navigator_contacts(self):
        assert _contains("navigator.contacts") and _contains("function select()")

    def test_window_controls_overlay(self):
        assert _contains("navigator.windowControlsOverlay") and _contains("getTitlebarAreaRect")


# ---------------------------------------------------------------------------
# Chromium args
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChromiumArgs:
    """Verify stealth-related Chromium flags are present."""

    def test_webrtc_ip_leak_prevention(self):
        """The WebRTC flag must be in Browser.start's default chromium_args."""
        import inspect

        source = inspect.getsource(Browser.start)
        assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in source
