"""Tests that stealth init scripts contain the expected patches.

These are marker tests — they verify that each critical section exists in the
script string so accidental deletions or regressions are caught early.  They
do NOT execute the JavaScript; runtime behavior is validated via live browser
testing against bot-detection sites.
"""

import inspect

import pytest

from tools.browser.core.browser import Browser, _ANTI_BOT_SCRIPT


# ---------------------------------------------------------------------------
# Webdriver patch — the only patch needed for real Chrome
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWebdriverPatch:
    """navigator.webdriver removal.

    The property is deleted entirely so navigator.webdriver is undefined,
    matching a real non-automated browser.  Redefining it as false is
    detectable by fp-collect which checks for existence, not just value.
    """

    def test_deletes_prototype_property(self):
        assert "delete Navigator.prototype.webdriver" in _ANTI_BOT_SCRIPT

    def test_deletes_instance_property(self):
        assert "delete navigator.webdriver" in _ANTI_BOT_SCRIPT

    def test_does_not_redefine_property(self):
        assert "Object.defineProperty(navigator, 'webdriver'" not in _ANTI_BOT_SCRIPT
        assert "Object.defineProperty(Navigator.prototype, 'webdriver'" not in _ANTI_BOT_SCRIPT

    def test_has_make_native_helper(self):
        assert "_makeNative" in _ANTI_BOT_SCRIPT


# ---------------------------------------------------------------------------
# Chrome args
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChromeArgs:
    """Verify stealth-related Chrome flags are present."""

    def test_webrtc_ip_leak_prevention(self):
        source = inspect.getsource(Browser.start)
        assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in source

    def test_always_uses_system_chrome(self):
        source = inspect.getsource(Browser.start)
        assert 'channel="chrome"' in source

    def test_webgl_flags_present(self):
        """WebGL-enabling flags are included in chrome_args (BTI-005, BTI-008)."""
        source = inspect.getsource(Browser.start)
        assert "--enable-webgl" in source
        assert "--enable-webgl2-compute-context" in source


# ---------------------------------------------------------------------------
# WebGL anti-bot script patch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWebGLPatch:
    """WebGL getContext override in the anti-bot script (BTI-005, BTI-008)."""

    def test_getcontext_override_present(self):
        """Anti-bot script patches HTMLCanvasElement.prototype.getContext."""
        assert "HTMLCanvasElement.prototype.getContext" in _ANTI_BOT_SCRIPT

    def test_webgl_context_types_handled(self):
        """Script handles webgl, webgl2, and experimental-webgl context types."""
        assert "'webgl'" in _ANTI_BOT_SCRIPT
        assert "'webgl2'" in _ANTI_BOT_SCRIPT
        assert "'experimental-webgl'" in _ANTI_BOT_SCRIPT

    def test_fallback_with_fail_if_major_performance_caveat(self):
        """Script retries with failIfMajorPerformanceCaveat=false on failure."""
        assert "failIfMajorPerformanceCaveat" in _ANTI_BOT_SCRIPT


# ---------------------------------------------------------------------------
# Permissions anti-bot patch (BTI-002, BTI-007, BTI-013, BTI-035)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPermissionsPatch:
    """navigator.permissions.query override in the anti-bot script."""

    def test_permissions_query_override_present(self):
        """Anti-bot script patches Permissions.prototype.query."""
        assert "Permissions.prototype.query" in _ANTI_BOT_SCRIPT

    def test_notifications_denied_response(self):
        """Script returns 'denied' state for notifications permission."""
        assert "'denied'" in _ANTI_BOT_SCRIPT
        assert "notifications" in _ANTI_BOT_SCRIPT

    def test_permissions_query_marked_native(self):
        """Permissions.prototype.query is marked as native via _makeNative."""
        assert "_makeNative(Permissions.prototype.query" in _ANTI_BOT_SCRIPT


# ---------------------------------------------------------------------------
# Chrome args for anti-bot (BTI-002, BTI-007, BTI-013, BTI-035)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAntiBotChromeArgs:
    """Verify anti-bot Chrome flags are present."""

    def test_translate_ui_disabled(self):
        """TranslateUI feature is disabled to reduce automation signal."""
        source = inspect.getsource(Browser.start)
        assert "--disable-features=TranslateUI" in source

    def test_optimization_guide_disabled(self):
        """OptimizationGuideModelDownloading feature is disabled."""
        source = inspect.getsource(Browser.start)
        assert "--disable-features=OptimizationGuideModelDownloading" in source
