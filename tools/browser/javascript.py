"""JavaScript execution tool for advanced browser automation."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel

from tools._truncation import truncate_args
from tools.browser.core import get_active_view
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.events import emit_screenshot

logger = logging.getLogger(__name__)


class JavaScriptResult(BaseModel):
    """Result of JavaScript execution.

    Attributes:
        success: True if JavaScript executed without errors.
        result: The JSON-serialized return value of the JavaScript code.
        console_output: Captured console.log/warn/error output during execution.
        error: Error message if execution failed, None otherwise.
    """

    success: bool
    result: Any | None = None
    console_output: list[str] | None = None
    error: str | None = None


@truncate_args(code=500)
async def execute_javascript(code: str, timeout_ms: int = 10000) -> JavaScriptResult:
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
        JavaScriptResult with success status, result value, and any error message.

    Raises:
        BrowserToolError: If browser is not initialized or page is not available.
    """
    _browser, view = await get_active_view("execute_javascript")

    logger.info("Executing JavaScript on page %s", view.url)
    logger.debug("JavaScript code: %s", code)

    # Capture console output during execution
    console_lines: list[str] = []
    page = await _browser.current_page()

    def _on_console(msg: Any) -> None:
        text = msg.text
        if text:
            console_lines.append(text)

    page.on("console", _on_console)

    try:
        # Execute the JavaScript with asyncio timeout
        result_value = await asyncio.wait_for(
            view.frame.evaluate(code),
            timeout=timeout_ms / 1000,  # convert ms to seconds
        )

        logger.info("JavaScript executed successfully")
        logger.debug("Result: %s", result_value)

        try:
            await emit_screenshot(page)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to emit screenshot after JS execution")

        return JavaScriptResult(
            success=True,
            result=result_value,
            console_output=console_lines or None,
            error=None,
        )

    except TimeoutError:
        error_msg = f"JavaScript execution timed out after {timeout_ms}ms"
        logger.warning(error_msg)
        return JavaScriptResult(
            success=False,
            result=None,
            console_output=console_lines or None,
            error=error_msg,
        )

    except PlaywrightTimeoutError as e:
        error_msg = f"JavaScript execution timed out after {timeout_ms}ms: {e}"
        logger.warning(error_msg)
        return JavaScriptResult(
            success=False,
            result=None,
            console_output=console_lines or None,
            error=error_msg,
        )

    except PlaywrightError as e:
        error_msg = f"JavaScript execution failed: {e}"
        logger.warning("JavaScript execution failed: %s", e)
        return JavaScriptResult(
            success=False,
            result=None,
            console_output=console_lines or None,
            error=error_msg,
        )

    except json.JSONDecodeError as e:
        error_msg = f"JavaScript return value is not JSON-serializable: {e}"
        logger.warning(error_msg)
        return JavaScriptResult(
            success=False,
            result=None,
            console_output=console_lines or None,
            error=error_msg,
        )

    except Exception as e:
        error_msg = f"Unexpected error during JavaScript execution: {e}"
        logger.exception("Unexpected error executing JavaScript")
        return JavaScriptResult(
            success=False,
            result=None,
            console_output=console_lines or None,
            error=error_msg,
        )

    finally:
        page.remove_listener("console", _on_console)


__all__ = ["JavaScriptResult", "execute_javascript"]
