"""JavaScript execution tool for advanced browser automation."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel

from tools.browser.core import get_browser
from tools.browser.core.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


class JavaScriptResult(BaseModel):
    """Result of JavaScript execution.

    Attributes:
        success: True if JavaScript executed without errors.
        result: The JSON-serialized return value of the JavaScript code.
        error: Error message if execution failed, None otherwise.
    """

    success: bool
    result: Any | None = None
    error: str | None = None


async def execute_javascript(code: str, timeout_ms: int = 10000) -> JavaScriptResult:
    """Execute arbitrary JavaScript in the current page context.

    WARNING: This is an advanced tool. Prefer structured tools (click, fill_field,
    snapshot, etc.) for reliability and debuggability. Only use this when
    structured tools cannot accomplish the task.

    The JavaScript code is executed in the page's main frame context and has
    access to the DOM, window object, and all page JavaScript. The return value
    must be JSON-serializable.

    Args:
        code: JavaScript code to execute. Can be a function expression or statement.
        timeout_ms: Maximum time to wait for execution in milliseconds.

    Returns:
        JavaScriptResult with success status, result value, and any error message.

    Raises:
        BrowserToolError: If browser is not initialized or page is not available.

    Examples:
        Extract custom data:
            result = await execute_javascript(
                "() => Array.from(document.querySelectorAll('.item')).map(el => ({
                    title: el.querySelector('h2').textContent,
                    price: el.querySelector('.price').textContent
                }))"
            )

        Remove popup:
            await execute_javascript("document.querySelector('#modal').remove()")

        Check page state:
            result = await execute_javascript("return window.location.href")
    """
    browser = await get_browser()
    page = await browser.current_page()

    if page is None or page.url in {"", "about:blank"}:
        msg = "No active page. Call open_url() first to navigate to a page."
        raise BrowserToolError(msg, tool="execute_javascript")

    logger.info("Executing JavaScript on page %s", page.url)
    logger.debug("JavaScript code: %s", code)

    try:
        # Execute the JavaScript with asyncio timeout
        result_value = await asyncio.wait_for(
            page.evaluate(code),
            timeout=timeout_ms / 1000,  # convert ms to seconds
        )

        logger.info("JavaScript executed successfully")
        logger.debug("Result: %s", result_value)

        return JavaScriptResult(
            success=True,
            result=result_value,
            error=None,
        )

    except TimeoutError:
        error_msg = f"JavaScript execution timed out after {timeout_ms}ms"
        logger.warning(error_msg)
        return JavaScriptResult(
            success=False,
            result=None,
            error=error_msg,
        )

    except PlaywrightTimeoutError as e:
        error_msg = f"JavaScript execution timed out after {timeout_ms}ms: {e}"
        logger.warning(error_msg)
        return JavaScriptResult(
            success=False,
            result=None,
            error=error_msg,
        )

    except PlaywrightError as e:
        error_msg = f"JavaScript execution failed: {e}"
        logger.warning("JavaScript execution failed: %s", e)
        return JavaScriptResult(
            success=False,
            result=None,
            error=error_msg,
        )

    except json.JSONDecodeError as e:
        error_msg = f"JavaScript return value is not JSON-serializable: {e}"
        logger.warning(error_msg)
        return JavaScriptResult(
            success=False,
            result=None,
            error=error_msg,
        )

    except Exception as e:
        error_msg = f"Unexpected error during JavaScript execution: {e}"
        logger.exception("Unexpected error executing JavaScript")
        return JavaScriptResult(
            success=False,
            result=None,
            error=error_msg,
        )


__all__ = ["JavaScriptResult", "execute_javascript"]
