"""JavaScript execution tool for advanced browser automation."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from tools._truncation import truncate_args
from tools.browser.core import get_active_view
from tools.browser.core._formatting import format_javascript_result
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.events import emit_screenshot

logger = logging.getLogger(__name__)
_console = Console(stderr=True)

_CODE_PREVIEW_LEN = 120


@truncate_args(code=500)
async def execute_javascript(code: str, timeout_ms: int = 10000) -> str:
    """Execute JavaScript in the page context.  Advanced — prefer structured tools.

    Only use when ``click()``, ``fill_field()``, ``browse_page()`` cannot
    accomplish the task.  Useful for removing popups, extracting custom data
    structures, or checking page state.

    ``console.log()`` output is captured in the ``console_output`` field.
    Use ``return`` for structured data — return values must be JSON-serializable.

    Args:
        code: JavaScript code or function expression to execute.
        timeout_ms: Maximum wait time in milliseconds (default 10000).

    Returns:
        Formatted string with success/error status, result, and console output.

    Raises:
        BrowserToolError: If browser is not initialized or page is not available.
    """
    _browser, view = await get_active_view("execute_javascript")

    # Capture console output during execution
    console_lines: list[str] = []
    page = await _browser.current_page()

    def _on_console(msg: Any) -> None:
        text = msg.text
        if text:
            console_lines.append(text)

    page.on("console", _on_console)

    code_preview = code.strip().replace("\n", " ")
    if len(code_preview) > _CODE_PREVIEW_LEN:
        code_preview = code_preview[:_CODE_PREVIEW_LEN] + "…"

    t0 = time.perf_counter()
    try:
        result_value = await asyncio.wait_for(
            view.frame.evaluate(code),
            timeout=timeout_ms / 1000,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        try:
            await emit_screenshot(page)
        except Exception:  # noqa: BLE001
            pass

        _print_js_panel(
            success=True,
            code_preview=code_preview,
            url=view.url,
            elapsed_ms=elapsed_ms,
            result=result_value,
            console_lines=console_lines,
        )

        return format_javascript_result(
            success=True,
            result=result_value,
            console_output=console_lines or None,
        )

    except TimeoutError:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        error_msg = f"JavaScript execution timed out after {timeout_ms}ms"
        _print_js_panel(
            success=False,
            code_preview=code_preview,
            url=view.url,
            elapsed_ms=elapsed_ms,
            error=error_msg,
            console_lines=console_lines,
        )
        return format_javascript_result(
            success=False,
            console_output=console_lines or None,
            error=error_msg,
        )

    except PlaywrightTimeoutError as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        error_msg = f"JavaScript execution timed out after {timeout_ms}ms: {e}"
        _print_js_panel(
            success=False,
            code_preview=code_preview,
            url=view.url,
            elapsed_ms=elapsed_ms,
            error=error_msg,
            console_lines=console_lines,
        )
        return format_javascript_result(
            success=False,
            console_output=console_lines or None,
            error=error_msg,
        )

    except PlaywrightError as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        error_msg = f"JavaScript execution failed: {e}"
        _print_js_panel(
            success=False,
            code_preview=code_preview,
            url=view.url,
            elapsed_ms=elapsed_ms,
            error=error_msg,
            console_lines=console_lines,
        )
        return format_javascript_result(
            success=False,
            console_output=console_lines or None,
            error=error_msg,
        )

    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        error_msg = f"Unexpected error during JavaScript execution: {e}"
        logger.exception("Unexpected error executing JavaScript")
        _print_js_panel(
            success=False,
            code_preview=code_preview,
            url=view.url,
            elapsed_ms=elapsed_ms,
            error=error_msg,
            console_lines=console_lines,
        )
        return format_javascript_result(
            success=False,
            console_output=console_lines or None,
            error=error_msg,
        )

    finally:
        page.remove_listener("console", _on_console)


def _print_js_panel(
    *,
    success: bool,
    code_preview: str,
    url: str,
    elapsed_ms: float,
    result: Any = None,
    error: str | None = None,
    console_lines: list[str] | None = None,
) -> None:
    """Print a Rich panel summarizing a JavaScript execution."""
    status = "[bold green]OK[/bold green]" if success else "[bold red]FAIL[/bold red]"
    title = f"[bold yellow]execute_javascript[/bold yellow]  {status}"

    body = Text()
    body.append(code_preview, style="dim")

    if success and result is not None:
        result_str = str(result)
        if len(result_str) > 200:
            result_str = result_str[:200] + "…"
        body.append("\nresult: ", style="bold")
        body.append(result_str, style="green")
    elif error:
        body.append("\nerror: ", style="bold")
        body.append(error, style="red")

    if console_lines:
        body.append(f"\nconsole: ", style="bold")
        preview = "; ".join(console_lines)
        if len(preview) > 200:
            preview = preview[:200] + "…"
        body.append(preview, style="dim cyan")

    display_url = url if len(url) <= 80 else url[:77] + "…"
    subtitle = f"[bold]{elapsed_ms:.0f}ms[/bold]  {display_url}"

    _console.print(Panel(
        body,
        title=title,
        subtitle=subtitle,
        border_style="yellow" if success else "red",
        expand=False,
    ))


__all__ = ["execute_javascript"]
