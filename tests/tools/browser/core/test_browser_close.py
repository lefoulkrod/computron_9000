import asyncio
import logging
import os
import pytest

from pathlib import Path

from tools.browser.core.browser import Browser


class DummyContext:
    def __init__(self, fail_once: bool = False, hang: bool = False) -> None:
        self._closed_calls: int = 0
        self._fail_once = fail_once
        self._hang = hang
        self.pages: list[object] = []

    async def close(self) -> None:  # type: ignore[override]
        self._closed_calls += 1
        if self._hang:
            await asyncio.sleep(9999)
        if self._fail_once and self._closed_calls == 1:
            from playwright.async_api import Error as PlaywrightError
            raise PlaywrightError("simulated close failure")


class DummyPW:
    def __init__(self, fail: bool = False, hang: bool = False) -> None:
        self.stopped: bool = False
        self._fail = fail
        self._hang = hang

    async def stop(self) -> None:  # type: ignore[override]
        if self._hang:
            await asyncio.sleep(9999)
        self.stopped = True
        if self._fail:
            from playwright.async_api import Error as PlaywrightError
            raise PlaywrightError("simulated stop failure")


class DummyPage:
    """Fake page that can simulate a hanging close."""

    def __init__(self, url: str = "https://example.com", hang: bool = False) -> None:
        self.url = url
        self._closed = False
        self._hang = hang

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        if self._hang:
            await asyncio.sleep(9999)
        self._closed = True


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_context_timeout(caplog: pytest.LogCaptureFixture) -> None:
    """Browser.close should not hang when context.close() blocks indefinitely."""
    ctx = DummyContext(hang=True)
    pw = DummyPW()
    browser = Browser(context=ctx, extra_headers={}, pw=pw)  # type: ignore[arg-type]
    # Shorten timeouts so the test is fast.
    browser._CONTEXT_CLOSE_TIMEOUT_S = 0.1  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING):
        await asyncio.wait_for(browser.close(), timeout=2.0)

    assert any("Timed out closing BrowserContext" in m for m in caplog.text.splitlines())
    # Driver stop should still have been called.
    assert pw.stopped is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_page_timeout(caplog: pytest.LogCaptureFixture) -> None:
    """Browser.close should not hang when a page.close() blocks."""
    hanging_page = DummyPage(hang=True)
    ctx = DummyContext()
    ctx.pages = [hanging_page]  # type: ignore[assignment]
    pw = DummyPW()
    browser = Browser(context=ctx, extra_headers={}, pw=pw)  # type: ignore[arg-type]
    browser._PAGE_CLOSE_TIMEOUT_S = 0.1  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING):
        await asyncio.wait_for(browser.close(), timeout=2.0)

    assert any("Timed out closing page" in m for m in caplog.text.splitlines())
    # Context and driver still closed.
    assert ctx._closed_calls == 1
    assert pw.stopped is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_driver_timeout(caplog: pytest.LogCaptureFixture) -> None:
    """Browser.close should not hang when pw.stop() blocks."""
    ctx = DummyContext()
    pw = DummyPW(hang=True)
    browser = Browser(context=ctx, extra_headers={}, pw=pw)  # type: ignore[arg-type]
    browser._PW_STOP_TIMEOUT_S = 0.1  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING):
        await asyncio.wait_for(browser.close(), timeout=2.0)

    assert any("Timed out stopping Playwright driver" in m for m in caplog.text.splitlines())
    assert ctx._closed_calls == 1


# --- Stale lock cleanup tests ---


@pytest.mark.unit
def test_cleanup_stale_lock_dead_pid(tmp_path: Path) -> None:
    """Stale lock pointing to a dead PID should be removed."""
    lock = tmp_path / "SingletonLock"
    cookie = tmp_path / "SingletonCookie"
    socket = tmp_path / "SingletonSocket"

    # Use PID 1999999999 which almost certainly doesn't exist.
    lock.symlink_to("testhost-1999999999")
    cookie.symlink_to("12345")
    socket.symlink_to("/tmp/fake")

    Browser._cleanup_stale_profile_locks(tmp_path)

    assert not lock.exists() and not lock.is_symlink()
    assert not cookie.exists() and not cookie.is_symlink()
    assert not socket.exists() and not socket.is_symlink()


@pytest.mark.unit
def test_cleanup_stale_lock_alive_pid(tmp_path: Path) -> None:
    """Lock pointing to our own PID (alive) should be left alone."""
    lock = tmp_path / "SingletonLock"
    # Point to our own PID — guaranteed to be alive.
    lock.symlink_to(f"testhost-{os.getpid()}")

    Browser._cleanup_stale_profile_locks(tmp_path)

    assert lock.is_symlink()


@pytest.mark.unit
def test_cleanup_no_lock(tmp_path: Path) -> None:
    """No lock file at all should be a no-op."""
    Browser._cleanup_stale_profile_locks(tmp_path)  # Should not raise
