"""Tests for shadow DOM traversal in the DOM walker.

Verifies that _ANNOTATED_SNAPSHOT_JS correctly discovers elements
inside shadow roots — both open and forced-open (via the init script
that patches attachShadow).
"""

import asyncio

import pytest
from playwright.async_api import async_playwright

from tools.browser.core.browser import _OPEN_SHADOW_DOM_SCRIPT

# Minimal HTML pages for testing shadow DOM scenarios

_OPEN_SHADOW_PAGE = """
<!DOCTYPE html><html><body>
<h1>Shadow DOM Test</h1>
<div id="host"></div>
<script>
  const host = document.getElementById('host');
  const shadow = host.attachShadow({ mode: 'open' });
  shadow.innerHTML = '<button id="shadow-btn">PRESS & HOLD</button><p>Shadow text</p>';
</script>
</body></html>
"""

_CLOSED_SHADOW_PAGE = """
<!DOCTYPE html><html><body>
<h1>Closed Shadow Test</h1>
<div id="host"></div>
<script>
  const host = document.getElementById('host');
  const shadow = host.attachShadow({ mode: 'closed' });
  shadow.innerHTML = '<button id="shadow-btn">Secret Button</button><p>Hidden text</p>';
</script>
</body></html>
"""

_SLOT_SHADOW_PAGE = """
<!DOCTYPE html><html><body>
<h1>Slot Test</h1>
<div id="host"><span slot="label">Slotted Label</span></div>
<script>
  const host = document.getElementById('host');
  const shadow = host.attachShadow({ mode: 'open' });
  shadow.innerHTML = `
    <div>
      <slot name="label"></slot>
      <button>Shadow Action</button>
      <p>After slot content</p>
    </div>
  `;
</script>
</body></html>
"""

_NESTED_SHADOW_PAGE = """
<!DOCTYPE html><html><body>
<h1>Nested Shadow Test</h1>
<div id="outer-host"></div>
<script>
  const outer = document.getElementById('outer-host');
  const outerShadow = outer.attachShadow({ mode: 'open' });
  outerShadow.innerHTML = '<div id="inner-host"></div><p>Outer shadow text</p>';
  const inner = outerShadow.getElementById('inner-host');
  const innerShadow = inner.attachShadow({ mode: 'open' });
  innerShadow.innerHTML = '<button>Deeply Nested Button</button>';
</script>
</body></html>
"""


def _read_snapshot_js():
    """Read the _ANNOTATED_SNAPSHOT_JS from page_view module."""
    from tools.browser.core.page_view import _ANNOTATED_SNAPSHOT_JS

    return _ANNOTATED_SNAPSHOT_JS


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def snapshot_js():
    return _read_snapshot_js()


async def _run_snapshot(html: str, snapshot_js: str, *, use_init_script: bool = False) -> str:
    """Launch a browser, load HTML, run the DOM walker, return content."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()
        if use_init_script:
            await context.add_init_script(_OPEN_SHADOW_DOM_SCRIPT)
        page = await context.new_page()
        await page.set_content(html)
        result = await page.evaluate(
            snapshot_js,
            {"budget": 8000, "scopeQuery": None, "nameLimit": 150, "fullPage": True},
        )
        await browser.close()
        return result["content"]


@pytest.mark.integration
class TestShadowDOMWalker:
    """Shadow DOM traversal in _ANNOTATED_SNAPSHOT_JS."""

    @pytest.mark.asyncio
    async def test_open_shadow_dom_button_visible(self, snapshot_js):
        """Walker discovers button inside an open shadow root."""
        content = await _run_snapshot(_OPEN_SHADOW_PAGE, snapshot_js)
        assert "[button] PRESS & HOLD" in content
        assert "Shadow text" in content

    @pytest.mark.asyncio
    async def test_closed_shadow_dom_invisible_without_patch(self, snapshot_js):
        """Walker cannot see inside closed shadow roots without init script."""
        content = await _run_snapshot(_CLOSED_SHADOW_PAGE, snapshot_js)
        assert "Secret Button" not in content
        assert "Hidden text" not in content

    @pytest.mark.asyncio
    async def test_closed_shadow_dom_visible_with_patch(self, snapshot_js):
        """Init script forces closed shadow roots open, making content visible."""
        content = await _run_snapshot(
            _CLOSED_SHADOW_PAGE, snapshot_js, use_init_script=True
        )
        assert "[button] Secret Button" in content
        assert "Hidden text" in content

    @pytest.mark.asyncio
    async def test_slot_rendering_order(self, snapshot_js):
        """Slotted content appears in shadow tree order, not light DOM order."""
        content = await _run_snapshot(_SLOT_SHADOW_PAGE, snapshot_js)
        # Slotted label should appear before the shadow button
        label_pos = content.find("Slotted Label")
        button_pos = content.find("[button] Shadow Action")
        after_pos = content.find("After slot content")
        assert label_pos >= 0, f"Slotted label not found in: {content}"
        assert button_pos >= 0, f"Shadow button not found in: {content}"
        assert after_pos >= 0, f"After-slot text not found in: {content}"
        assert label_pos < button_pos < after_pos, (
            f"Wrong order: label={label_pos}, button={button_pos}, after={after_pos}\n{content}"
        )

    @pytest.mark.asyncio
    async def test_nested_shadow_dom(self, snapshot_js):
        """Walker traverses nested shadow roots recursively."""
        content = await _run_snapshot(_NESTED_SHADOW_PAGE, snapshot_js)
        assert "[button] Deeply Nested Button" in content
        assert "Outer shadow text" in content

    @pytest.mark.asyncio
    async def test_heading_still_visible_with_shadow(self, snapshot_js):
        """Light DOM heading is still visible alongside shadow content."""
        content = await _run_snapshot(_OPEN_SHADOW_PAGE, snapshot_js)
        assert "[h1] Shadow DOM Test" in content
