"""Shared wait helpers for browser interactions."""

from __future__ import annotations

import logging

from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    Page,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from config import BrowserWaitConfig

logger = logging.getLogger(__name__)


async def wait_for_page_settle(
    page: Page,
    *,
    expect_navigation: bool,
    waits: BrowserWaitConfig,
) -> None:
    """Wait for network and DOM activity to quiet after an interaction."""
    try:
        if expect_navigation and hasattr(page, "wait_for_load_state"):
            try:
                await page.wait_for_load_state("networkidle", timeout=waits.post_navigation_idle_timeout_ms)
            except PlaywrightTimeoutError:
                logger.debug(
                    "post-navigation networkidle wait timed out after %d ms",
                    waits.post_navigation_idle_timeout_ms,
                )
        elif expect_navigation:
            logger.debug("Page object has no wait_for_load_state; skipping networkidle wait")

        if not hasattr(page, "wait_for_function"):
            logger.debug("Page object has no wait_for_function; skipping DOM quiet wait")
            return

        dom_quiet_ms = max(0, waits.dom_quiet_window_ms)
        js = f"""() => {{
            return new Promise((resolve) => {{
                const quiet = {dom_quiet_ms};
                let timer = setTimeout(() => {{ resolve(true); }}, quiet);
                const obs = new MutationObserver((mutations) => {{
                    // Filter out mutations from form input typing
                    const significantMutation = mutations.some(m => {{
                        // Ignore value attribute changes on inputs/textareas
                        if (m.type === 'attributes' && m.attributeName === 'value') {{
                            const target = m.target;
                            if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {{
                                return false;
                            }}
                        }}
                        // Ignore characterData changes inside input/textarea
                        if (m.type === 'characterData') {{
                            let node = m.target.parentNode;
                            while (node) {{
                                if (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') {{
                                    return false;
                                }}
                                node = node.parentNode;
                            }}
                        }}
                        return true;
                    }});
                    
                    if (significantMutation) {{
                        clearTimeout(timer);
                        timer = setTimeout(() => {{ obs.disconnect(); resolve(true); }}, quiet);
                    }}
                }});
                try {{
                    obs.observe(document, {{ childList: true, subtree: true, attributes: true, characterData: true }});
                }} catch (e) {{
                    clearTimeout(timer);
                    resolve(true);
                }}
            }});
        }}"""
        await page.wait_for_function(js, timeout=waits.dom_mutation_timeout_ms)
    except PlaywrightTimeoutError:
        logger.debug("DOM mutation quiet wait timed out after %d ms", waits.dom_mutation_timeout_ms)
    except PlaywrightError as exc:
        logger.debug("Error while waiting for page settle: %s", exc)


__all__ = ["wait_for_page_settle"]
