"""Tests for shadow DOM traversal in the DOM walker.

Verifies that _STRUCTURED_SNAPSHOT_JS correctly discovers elements
inside shadow roots — both open and forced-open (via the init script
that patches attachShadow).
"""

import asyncio

import pytest
from playwright.async_api import async_playwright

from tools.browser.core.browser import _OPEN_SHADOW_DOM_SCRIPT
from tools.browser.core._pipeline import process_snapshot

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

_ARIA_HIDDEN_DIALOG_PAGE = """
<!DOCTYPE html><html><body>
<div aria-hidden="true">
  <p>Background content</p>
  <div role="dialog" aria-label="Calendar">
    <button>15</button>
    <button>16</button>
    <button>Done</button>
  </div>
</div>
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

# Nested slot delegation (Reddit-style): light DOM children projected through
# two shadow boundaries via slot-to-slot chaining.
_NESTED_SLOT_DELEGATION_PAGE = """
<!DOCTYPE html><html><body>
<h1>Nested Slot Delegation</h1>
<app-shell>
  <button id="projected-btn">Projected Button</button>
  <a href="#projected">Projected Link</a>
</app-shell>
<script>
  // Inner wrapper: shadow contains <div><slot></div>
  class AppWrapper extends HTMLElement {
    constructor() {
      super();
      const shadow = this.attachShadow({ mode: 'open' });
      shadow.innerHTML = '<div><slot></slot></div>';
    }
  }
  customElements.define('app-wrapper', AppWrapper);

  // Outer shell: shadow contains <app-wrapper><slot></app-wrapper>
  // The <slot> in the shadow is the light child of app-wrapper, creating
  // a slot-to-slot chain: app-shell light -> outer slot -> inner slot -> rendered
  class AppShell extends HTMLElement {
    constructor() {
      super();
      const shadow = this.attachShadow({ mode: 'open' });
      shadow.innerHTML = '<app-wrapper><slot></slot></app-wrapper>';
    }
  }
  customElements.define('app-shell', AppShell);
</script>
</body></html>
"""

# Zero-rect shadow host: custom element with display:contents renders via shadow root
# but the host element itself has a 0x0 bounding rect.
_ZERO_RECT_SHADOW_HOST_PAGE = """
<!DOCTYPE html><html><body>
<h1>Zero-Rect Shadow Host</h1>
<zero-host></zero-host>
<script>
  class ZeroHost extends HTMLElement {
    constructor() {
      super();
      const shadow = this.attachShadow({ mode: 'open' });
      shadow.innerHTML = `
        <style>:host { display: contents; }</style>
        <button>Inside Zero-Rect Host</button>
        <a href="#zero-link">Zero Host Link</a>
      `;
    }
  }
  customElements.define('zero-host', ZeroHost);
</script>
</body></html>
"""

# Triple-nested slot delegation: three levels of shadow DOM.
_TRIPLE_NESTED_SLOT_PAGE = """
<!DOCTYPE html><html><body>
<h1>Triple Nested</h1>
<level-one>
  <button>Triple Deep Button</button>
</level-one>
<script>
  class LevelThree extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' }).innerHTML = '<div><slot></slot></div>';
    }
  }
  customElements.define('level-three', LevelThree);

  class LevelTwo extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' }).innerHTML = '<level-three><slot></slot></level-three>';
    }
  }
  customElements.define('level-two', LevelTwo);

  class LevelOne extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' }).innerHTML = '<level-two><slot></slot></level-two>';
    }
  }
  customElements.define('level-one', LevelOne);
</script>
</body></html>
"""


def _read_snapshot_js():
    """Read the _STRUCTURED_SNAPSHOT_JS from page_view module."""
    from tools.browser.core.page_view import _STRUCTURED_SNAPSHOT_JS

    return _STRUCTURED_SNAPSHOT_JS


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def snapshot_js():
    return _read_snapshot_js()


async def _run_snapshot(html: str, snapshot_js: str, *, use_init_script: bool = False) -> str:
    """Launch a browser, load HTML, run the structured walker + pipeline."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()
        if use_init_script:
            await context.add_init_script(_OPEN_SHADOW_DOM_SCRIPT)
        page = await context.new_page()
        await page.set_content(html)
        result = await page.evaluate(
            snapshot_js,
            {"fullPage": True},
        )
        await browser.close()
        content, _ = process_snapshot(
            result["nodes"],
            budget=8000,
            name_limit=150,
            full_page=True,
        )
        return content


@pytest.mark.integration
class TestShadowDOMWalker:
    """Shadow DOM traversal in _STRUCTURED_SNAPSHOT_JS."""

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


@pytest.mark.integration
class TestNestedSlotDelegation:
    """Slot-to-slot chaining across multiple shadow boundaries (Reddit pattern)."""

    @pytest.mark.asyncio
    async def test_nested_slot_delegation(self, snapshot_js):
        """Light DOM children projected through two shadow boundaries are visible."""
        content = await _run_snapshot(_NESTED_SLOT_DELEGATION_PAGE, snapshot_js)
        assert "[button] Projected Button" in content
        assert "[link] Projected Link" in content

    @pytest.mark.asyncio
    async def test_zero_rect_shadow_host(self, snapshot_js):
        """Shadow host with display:contents (0x0 rect) has visible shadow content."""
        content = await _run_snapshot(_ZERO_RECT_SHADOW_HOST_PAGE, snapshot_js)
        assert "[button] Inside Zero-Rect Host" in content
        assert "[link] Zero Host Link" in content

    @pytest.mark.asyncio
    async def test_triple_nested_slot_delegation(self, snapshot_js):
        """Light DOM children projected through three shadow boundaries are visible."""
        content = await _run_snapshot(_TRIPLE_NESTED_SLOT_PAGE, snapshot_js)
        assert "[button] Triple Deep Button" in content


@pytest.mark.integration
class TestAriaHiddenDialog:
    """Walker handles dialogs inside aria-hidden containers."""

    @pytest.mark.asyncio
    async def test_dialog_inside_aria_hidden_is_visible(self, snapshot_js):
        """Dialog inside aria-hidden ancestor is still walked."""
        content = await _run_snapshot(_ARIA_HIDDEN_DIALOG_PAGE, snapshot_js)
        assert "[button] Done" in content
        assert "[button] 15" in content
        assert "[button] 16" in content
