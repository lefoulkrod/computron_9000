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
