"""Shared wait helpers for browser interactions."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    Frame,
    Page,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from config import BrowserWaitConfig

logger = logging.getLogger(__name__)


@dataclass
class SettleTimings:
    """Per-phase timing data from wait_for_page_settle."""

    network_idle_ms: float = 0
    network_idle_timed_out: bool = False
    font_ms: float = 0
    font_timed_out: bool = False
    dom_quiet_ms: float = 0
    dom_quiet_timed_out: bool = False
    animation_ms: float = 0
    animation_timed_out: bool = False
    error: str | None = None

    @property
    def total_ms(self) -> float:
        return self.network_idle_ms + self.font_ms + self.dom_quiet_ms + self.animation_ms

    @property
    def phases(self) -> list[tuple[str, float, bool]]:
        """Return (name, duration_ms, timed_out) for each phase."""
        return [
            ("network idle", self.network_idle_ms, self.network_idle_timed_out),
            ("fonts", self.font_ms, self.font_timed_out),
            ("DOM quiet", self.dom_quiet_ms, self.dom_quiet_timed_out),
            ("animations", self.animation_ms, self.animation_timed_out),
        ]


async def wait_for_page_settle(
    page: Page | Frame,
    *,
    waits: BrowserWaitConfig,
) -> SettleTimings:
    """Wait for network, fonts, DOM, and CSS animation activity to quiet.

    Four phases run in sequence:

    1. **Network idle** — waits for zero in-flight HTTP connections.
       Resolves instantly if the network is already idle.  Pages with
       persistent connections (SSE, long-polling) hit the timeout and
       move on.
    2. **Web fonts** — ``document.fonts.ready`` ensures fonts are parsed
       and applied before we snapshot, preventing text reflow (FOUT).
       Resolves near-instantly after networkidle since font HTTP
       requests are already complete.
    3. **DOM quiet** — a MutationObserver waits for a window of no
       significant mutations (ignores form-input value changes).  Also
       observes open shadow roots so web-component updates are caught.
    4. **CSS animations** — waits for short animations (≤ 1 s) to
       finish so modal slide-ins, fades, and skeleton transitions are
       fully rendered.  Capped to avoid blocking on infinite loops.

    Returns:
        SettleTimings with per-phase durations.
    """
    timings = SettleTimings()
    try:
        # Phase 1: network idle
        if hasattr(page, "wait_for_load_state"):
            t0 = time.monotonic()
            try:
                await page.wait_for_load_state(
                    "networkidle", timeout=waits.network_idle_timeout_ms,
                )
            except PlaywrightTimeoutError:
                timings.network_idle_timed_out = True
            timings.network_idle_ms = (time.monotonic() - t0) * 1000

        if not hasattr(page, "evaluate"):
            return timings

        # Phase 2: web fonts
        font_timeout_ms = max(0, waits.font_timeout_ms)
        font_js = f"""async () => {{
            try {{
                await Promise.race([
                    document.fonts.ready,
                    new Promise(r => setTimeout(r, {font_timeout_ms})),
                ]);
            }} catch {{}}
        }}"""
        t0 = time.monotonic()
        try:
            await page.evaluate(font_js)
        except PlaywrightTimeoutError:
            timings.font_timed_out = True
        timings.font_ms = (time.monotonic() - t0) * 1000

        # Phase 3: DOM quiet window (including shadow roots)
        if not hasattr(page, "wait_for_function"):
            return timings

        dom_quiet_ms = max(0, waits.dom_quiet_window_ms)
        dom_js = f"""() => {{
            return new Promise((resolve) => {{
                const quiet = {dom_quiet_ms};
                const observeOpts = {{ childList: true, subtree: true, attributes: true, characterData: true }};

                const isSignificant = (mutations) => mutations.some(m => {{
                    if (m.type === 'attributes' && m.attributeName === 'value') {{
                        const t = m.target;
                        if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA') return false;
                    }}
                    if (m.type === 'characterData') {{
                        let n = m.target.parentNode;
                        while (n) {{
                            if (n.tagName === 'INPUT' || n.tagName === 'TEXTAREA') return false;
                            n = n.parentNode;
                        }}
                    }}
                    return true;
                }});

                let timer = setTimeout(() => {{ obs.disconnect(); resolve(true); }}, quiet);

                const resetTimer = () => {{
                    clearTimeout(timer);
                    timer = setTimeout(() => {{ obs.disconnect(); resolve(true); }}, quiet);
                }};

                const callback = (mutations) => {{
                    if (isSignificant(mutations)) resetTimer();
                    // Watch for new shadow roots in added nodes
                    for (const m of mutations) {{
                        if (m.type !== 'childList') continue;
                        for (const node of m.addedNodes) {{
                            if (node.nodeType === 1) observeShadowRoots(node);
                        }}
                    }}
                }};

                const obs = new MutationObserver(callback);

                // Recursively find and observe all open shadow roots
                const observeShadowRoots = (root) => {{
                    try {{
                        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                        let el = walker.currentNode;
                        while (el) {{
                            if (el.shadowRoot) {{
                                obs.observe(el.shadowRoot, observeOpts);
                                // Also walk inside the shadow root
                                observeShadowRoots(el.shadowRoot);
                            }}
                            el = walker.nextNode();
                        }}
                    }} catch {{}}
                }};

                try {{
                    obs.observe(document, observeOpts);
                    observeShadowRoots(document);
                }} catch (e) {{
                    clearTimeout(timer);
                    resolve(true);
                }}
            }});
        }}"""
        t0 = time.monotonic()
        try:
            await page.wait_for_function(dom_js, timeout=waits.dom_mutation_timeout_ms)
        except PlaywrightTimeoutError:
            timings.dom_quiet_timed_out = True
        timings.dom_quiet_ms = (time.monotonic() - t0) * 1000

        # Phase 4: wait for short CSS animations to finish.
        # Only waits on animations with duration ≤ 1s (modal fades,
        # slide-ins, skeleton transitions).  Long/infinite animations
        # are ignored.  The whole phase is capped at animation_timeout_ms.
        anim_timeout_ms = max(0, waits.animation_timeout_ms)
        anim_js = f"""async () => {{
            try {{
                const anims = document.getAnimations().filter(a => {{
                    try {{
                        const d = a.effect?.getComputedTiming()?.duration;
                        return typeof d === 'number' && d <= 1000;
                    }} catch {{ return false; }}
                }});
                if (anims.length > 0) {{
                    await Promise.race([
                        Promise.allSettled(anims.map(a => a.finished)),
                        new Promise(r => setTimeout(r, {anim_timeout_ms})),
                    ]);
                }}
            }} catch {{}}
        }}"""
        t0 = time.monotonic()
        try:
            await page.evaluate(anim_js)
        except PlaywrightTimeoutError:
            timings.animation_timed_out = True
        timings.animation_ms = (time.monotonic() - t0) * 1000
    except PlaywrightError as exc:
        timings.error = str(exc)

    return timings


__all__ = ["SettleTimings", "wait_for_page_settle"]
