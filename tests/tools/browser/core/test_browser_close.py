import pytest
import logging

from tools.browser.core.browser import Browser


class DummyContext:
    def __init__(self, fail_once: bool = False) -> None:
        self._closed_calls: int = 0
        self._fail_once = fail_once
        self.pages: list[object] = []

    async def close(self) -> None:  # type: ignore[override]
        self._closed_calls += 1
        if self._fail_once and self._closed_calls == 1:
            from playwright.async_api import Error as PlaywrightError
            raise PlaywrightError("simulated close failure")


class DummyPW:
    def __init__(self, fail: bool = False) -> None:
        self.stopped: bool = False
        self._fail = fail

    async def stop(self) -> None:  # type: ignore[override]
        self.stopped = True
        if self._fail:
            from playwright.async_api import Error as PlaywrightError
            raise PlaywrightError("simulated stop failure")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_swallows_context_exception(caplog: pytest.LogCaptureFixture) -> None:
    """Browser.close should suppress context close errors and still attempt driver stop."""
    ctx = DummyContext(fail_once=True)
    pw = DummyPW()
    browser = Browser(context=ctx, extra_headers={}, pw=pw)  # type: ignore[arg-type]
    with caplog.at_level(logging.WARNING):
        await browser.close()
    # Warning logged
    assert any("Suppressed exception while closing BrowserContext" in m for m in caplog.text.splitlines())
    # stop called
    assert pw.stopped is True
    # Second close is a no-op
    await browser.close()
    assert ctx._closed_calls == 1  # still only one attempt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_swallows_driver_exception(caplog: pytest.LogCaptureFixture) -> None:
    """Browser.close should suppress driver stop errors."""
    ctx = DummyContext()
    pw = DummyPW(fail=True)
    browser = Browser(context=ctx, extra_headers={}, pw=pw)  # type: ignore[arg-type]
    with caplog.at_level(logging.WARNING):
        await browser.close()
    assert any("Suppressed exception while stopping Playwright driver" in m for m in caplog.text.splitlines())
    # context closed exactly once
    assert ctx._closed_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_browser_function_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """close_browser should be safe when no browser exists."""
    import tools.browser.core.browser as mod

    # Ensure global _browser is None
    mod._browser = None  # type: ignore[attr-defined]
    await mod.close_browser()  # Should not raise

    # Set one then close twice
    ctx = DummyContext()
    pw = DummyPW()
    mod._browser = Browser(context=ctx, extra_headers={}, pw=pw)  # type: ignore[arg-type]
    await mod.close_browser()
    assert mod._browser is None
    # second call: still fine
    await mod.close_browser()
