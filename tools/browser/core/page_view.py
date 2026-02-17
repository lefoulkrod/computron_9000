"""Page view combining content and interactive elements.

Walks the DOM in document order, emitting both text content and interactive
element annotations in a single output.  Each interactive element is
rendered as ``[role] name`` — the ``role:name`` pair can be passed directly
to ``click()``, ``fill_field()``, and other interaction tools.

Design goals:
    * Single ``page.evaluate()`` round-trip for the entire DOM walk
    * Viewport-clipped by default to keep output small
    * Deterministic trimming rules (no heuristics)
    * Optional scoping to narrow output to a page section
    * Character budget to prevent context overflow
"""

from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = 4000
MAX_NAME_LEN = 150  # Increased from 80 to reduce truncation of long button names (e.g., Amazon Delete buttons)


class PageView(BaseModel):
    """Page view combining content and interactive elements.

    Attributes:
        title: Page title.
        url: Final URL after any redirects.
        status_code: HTTP status code (``None`` if not from a navigation).
        content: Annotated text mixing content and ``[role] name`` annotations.
        viewport: Current viewport/scroll state dict.
        truncated: Whether content was truncated by the character budget.
    """

    title: str
    url: str
    status_code: int | None = None
    content: str = ""
    viewport: dict[str, int] = {}
    truncated: bool = False


# ---------------------------------------------------------------------------
# JavaScript DOM walker
# ---------------------------------------------------------------------------
# Executed via a single page.evaluate() call.  Accepts a params object:
#   { budget: number, scopeQuery: string | null, nameLimit: number }
# Returns: { content: string, truncated: boolean }

_ANNOTATED_SNAPSHOT_JS = """
(params) => {
  const { budget, scopeQuery, nameLimit } = params;
  const vh = window.innerHeight;
  const vw = window.innerWidth;

  // ---- Role mapping ----
  function getRole(el) {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName;
    switch (tag) {
      case 'A': return el.hasAttribute('href') ? 'link' : null;
      case 'BUTTON': return 'button';
      case 'SELECT': return 'combobox';
      case 'TEXTAREA': return 'textbox';
      case 'INPUT': {
        const t = (el.getAttribute('type') || 'text').toLowerCase();
        const m = {
          text:'textbox', search:'searchbox', email:'textbox',
          password:'textbox', tel:'textbox', url:'textbox',
          number:'spinbutton', checkbox:'checkbox', radio:'radio',
          submit:'button', reset:'button', button:'button'
        };
        return m[t] || 'textbox';
      }
      case 'H1': case 'H2': case 'H3':
      case 'H4': case 'H5': case 'H6':
        return 'heading';
      case 'IMG': return 'img';
      case 'NAV': return 'navigation';
      case 'MAIN': return 'main';
      default: return null;
    }
  }

  const INTERACTIVE = new Set([
    'link','button','textbox','searchbox','checkbox','radio',
    'combobox','spinbutton','slider','switch','tab','menuitem',
    'option','treeitem'
  ]);

  // ---- Accessible name ----
  function getName(el) {
    // aria-label
    const al = el.getAttribute('aria-label');
    if (al) return al.trim();
    // aria-labelledby
    const lb = el.getAttribute('aria-labelledby');
    if (lb) {
      const ref = document.getElementById(lb);
      if (ref) return (ref.innerText || ref.textContent || '').trim();
    }
    // inputs: label[for] first (matches Playwright's accessible name), then placeholder, then value
    const tag = el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
      const id = el.getAttribute('id');
      if (id) {
        const lbl = document.querySelector('label[for="' + id + '"]');
        if (lbl) return lbl.textContent.trim();
      }
      const ph = el.getAttribute('placeholder');
      if (ph) return ph.trim();
      // submit/button/reset inputs store their visible text in the value attribute
      if (tag === 'INPUT') {
        const val = el.getAttribute('value');
        if (val) return val.trim();
      }
    }
    // img alt
    if (tag === 'IMG') return (el.getAttribute('alt') || '').trim();
    // innerText (for buttons, links, etc.)
    const t = el.innerText;
    return t ? t.trim() : '';
  }

  function truncName(n) {
    if (n.length <= nameLimit) return n;
    return n.substring(0, nameLimit) + '...';
  }

  // ---- Visibility / viewport ----
  const scrolled = window.scrollY > 50;

  function shouldSkip(el) {
    if (el.getAttribute('aria-hidden') === 'true') return 'skip-tree';
    const s = window.getComputedStyle(el);
    if (s.display === 'none') return 'skip-tree';
    if (s.visibility === 'hidden' || parseFloat(s.opacity) === 0) return 'skip-self';
    // When the page is scrolled, skip sticky/fixed containers — they are
    // navigation chrome that repeats on every viewport and wastes budget.
    if (scrolled && (s.position === 'sticky' || s.position === 'fixed')) return 'skip-tree';
    return null;
  }

  // Returns: 'visible' | 'clipped' | 'hidden'
  //   visible — element is in viewport and not clipped
  //   clipped — element is in viewport area but fully clipped by an
  //             overflow:hidden ancestor (e.g. CSS carousel panels).
  //             Children may still be visible so the walker should recurse.
  //   hidden  — element is entirely outside the viewport or zero-size
  function checkVisibility(el) {
    const r = el.getBoundingClientRect();
    // Zero-size elements with children should still recurse — the element
    // itself may be a CSS layout container (e.g. <main> on MDN) whose
    // children have their own dimensions.  Only truly empty leaf elements
    // are hidden.
    if (r.width === 0 && r.height === 0) {
      return el.children.length > 0 ? 'clipped' : 'hidden';
    }
    if (!(r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw)) {
      // Element rect is outside viewport.  However, if overflow is visible
      // (the CSS default) children may extend beyond the parent's box and
      // still be in the viewport.  Example: eBay search results live inside
      // a 31px-tall container whose children overflow 19 000+ px downward.
      // Check scrollHeight to detect this and recurse into children.
      if (el.children.length > 0) {
        const os = window.getComputedStyle(el);
        if (os.overflowY === 'visible' && el.scrollHeight > r.height + 1) {
          // Does the overflowing content reach the viewport?
          if (r.top + el.scrollHeight > 0 && r.top < vh) return 'clipped';
        }
        if (os.overflowX === 'visible' && el.scrollWidth > r.width + 1) {
          if (r.left + el.scrollWidth > 0 && r.left < vw) return 'clipped';
        }
      }
      return 'hidden';
    }
    // Check overflow clipping — an element may report an in-viewport rect
    // but actually be clipped by an ancestor with overflow:hidden/clip (e.g.
    // CSS carousel/slider tab panels on SolarWinds).  Only clip in the axis
    // that is actually hidden/clip to avoid false negatives.
    let ancestor = el.parentElement;
    while (ancestor && ancestor !== document.body) {
      const os = window.getComputedStyle(ancestor);
      const ox = os.overflowX;
      const oy = os.overflowY;
      const clipX = ox === 'hidden' || ox === 'clip';
      const clipY = oy === 'hidden' || oy === 'clip';
      if (clipX || clipY) {
        const ar = ancestor.getBoundingClientRect();
        if (clipX && (r.right <= ar.left || r.left >= ar.right)) return 'clipped';
        if (clipY && (r.bottom <= ar.top || r.top >= ar.bottom)) return 'clipped';
      }
      ancestor = ancestor.parentElement;
    }
    return 'visible';
  }

  const SKIP_ROLES = new Set(['presentation', 'none', 'separator']);

  // ---- Scoping ----
  function findScope(query) {
    if (!query) return document.body;
    const q = query.toLowerCase();
    // Search headings — prefer exact match over substring, h2 over h1
    // (h2 is typically a section heading, h1 is the page title)
    const headings = document.querySelectorAll('h2,h3,h4,h5,h6,h1');
    let bestMatch = null;
    for (const h of headings) {
      const text = (h.innerText || '').trim().toLowerCase();
      if (!text) continue;
      if (text === q) { bestMatch = h; break; }  // exact match wins
      if (!bestMatch && text.includes(q)) bestMatch = h;
    }
    if (bestMatch) return findContainer(bestMatch);
    // Search landmarks by aria-label
    const landmarks = document.querySelectorAll(
      'nav,[role=navigation],[role=region],[role=main],main,section,aside'
    );
    for (const lm of landmarks) {
      const label = lm.getAttribute('aria-label') || '';
      if (label.toLowerCase().includes(q)) return lm;
    }
    return null;
  }

  function findContainer(el) {
    // Walk up from the heading to find a substantial container.
    // Skip single-child wrapper divs — they're just layout noise.
    // A good container has multiple children (the heading + content).
    const semantic = new Set([
      'ARTICLE','SECTION','MAIN','ASIDE','NAV','TBODY',
      'TABLE','FORM','DETAILS','DIALOG','FIGURE'
    ]);
    let current = el.parentElement;
    let depth = 0;
    while (current && current !== document.body && depth < 15) {
      // Semantic container tags are always good
      if (semantic.has(current.tagName)) return current;
      const role = current.getAttribute('role');
      if (role && ['region','main','group'].includes(role)) return current;
      // A div/span with an id is likely a meaningful boundary
      if (current.id && current.children.length > 1) return current;
      // A div with multiple children is a good container
      if (current.children.length >= 3) return current;
      current = current.parentElement;
      depth++;
    }
    return current || document.body;
  }

  // ---- DOM walk ----
  const lines = [];
  let chars = 0;
  const seen = new Set();

  function emit(line) {
    if (chars >= budget || !line) return false;
    if (seen.has(line)) return true;
    seen.add(line);
    lines.push(line);
    chars += line.length + 1;
    return chars < budget;
  }

  function walk(el, isRoot) {
    if (chars >= budget) return;

    const skip = shouldSkip(el);
    if (skip === 'skip-tree') return;
    if (skip === 'skip-self') {
      // Still walk children (visibility:hidden children may be visible)
      for (const child of el.children) walk(child, false);
      return;
    }

    // Skip viewport check for the root element — on some sites (e.g.
    // Wikipedia) the <body> bounding rect doesn't span the full document
    // after scrolling due to CSS layout (sticky elements, flexbox), but
    // its children are still visible.
    if (!isRoot) {
      const vis = checkVisibility(el);
      if (vis === 'hidden') return;
      // Overflow-clipped: this element is clipped by an overflow:hidden
      // ancestor (e.g. a CSS carousel wrapper holding all tab panels).
      // Don't emit this element's own content, but recurse into children
      // — individual children may be positioned within the clip bounds.
      if (vis === 'clipped') {
        for (const child of el.children) walk(child, false);
        return;
      }
    }

    const role = getRole(el);

    // Skip decorative
    if (role && SKIP_ROLES.has(role)) return;

    // Interactive elements: emit annotation, don't walk children
    if (role && INTERACTIVE.has(role)) {
      let name = getName(el);
      if (!name) return;
      name = truncName(name);

      if (role === 'combobox' || el.tagName === 'SELECT') {
        const sel = el.querySelector('option:checked,option[selected]');
        const sv = sel ? sel.textContent.trim() : '';
        emit('[' + role + '] ' + name + (sv ? ' = ' + sv : ''));
      } else if (role === 'checkbox' || role === 'radio') {
        const checked = el.checked || el.getAttribute('aria-checked') === 'true';
        emit('[' + role + '] ' + name + (checked ? ' (checked)' : ''));
      } else {
        emit('[' + role + '] ' + name);
      }
      return;
    }

    // Headings
    if (role === 'heading') {
      const lvl = el.tagName.match(/H(\\d)/)?.[1] || '';
      const text = (el.innerText || '').trim();
      if (text) emit('[h' + lvl + '] ' + truncName(text));
      return;
    }

    // Images with alt text
    if (role === 'img') {
      const alt = (el.getAttribute('alt') || '').trim();
      if (alt) emit('[img] ' + truncName(alt));
      return;
    }

    // Leaf text node (no element children)
    if (el.children.length === 0) {
      const text = (el.innerText || '').trim();
      if (text && text.length > 1) {
        // Truncate long text blocks to keep output manageable
        emit(text.length > 200 ? text.substring(0, 200) + '...' : text);
      }
      return;
    }

    // Paragraph-like containers: emit innerText as a single chunk instead
    // of recursing into inline fragments (spans, bold, inline links, etc.).
    // Only applies to <p> and similar prose containers — NOT <li> or <td>
    // which often hold important interactive children.
    if (el.tagName === 'P' || el.tagName === 'BLOCKQUOTE' || el.tagName === 'FIGCAPTION') {
      const text = (el.innerText || '').trim();
      if (text && text.length > 1) {
        emit(text.length > 200 ? text.substring(0, 200) + '...' : text);
      }
      return;
    }

    // Recurse into children
    for (const child of el.children) {
      if (chars >= budget) break;
      walk(child, false);
    }
  }

  // Determine root
  let root = document.body;
  let scopeNotFound = false;
  if (scopeQuery) {
    const scoped = findScope(scopeQuery);
    if (scoped) {
      root = scoped;
    } else {
      scopeNotFound = true;
    }
  }

  walk(root, true);

  const prefix = scopeNotFound
    ? '[scope "' + scopeQuery + '" not found, showing full page]\\n'
    : '';

  return {
    content: prefix + lines.join('\\n'),
    truncated: chars >= budget
  };
}
"""


async def build_page_view(
    page: Page,
    response: Response | None,
    *,
    scope: str | None = None,
    budget: int = DEFAULT_BUDGET,
) -> PageView:
    """Build an annotated snapshot combining content and interactive elements.

    Args:
        page: A Playwright ``Page`` instance.
        response: Navigation response (may be ``None``).
        scope: Optional section name to scope to (matches headings/landmarks).
        budget: Character budget for the content field.

    Returns:
        ``PageView`` with annotated content, title, url, viewport info.
    """
    try:
        title: str = await page.title()
    except PlaywrightError:  # pragma: no cover - defensive
        logger.warning("Failed to read page title, defaulting to empty string")
        title = ""

    if response is not None:
        final_url = response.url
        status_code = response.status
    else:
        final_url = page.url
        status_code = None

    # Run JS DOM walk and viewport query in parallel
    try:
        walk_task = page.evaluate(
            _ANNOTATED_SNAPSHOT_JS,
            {"budget": budget, "scopeQuery": scope, "nameLimit": MAX_NAME_LEN},
        )

        viewport_task = page.evaluate(
            """() => ({
                scroll_top: Math.floor(window.scrollY),
                viewport_height: Math.floor(window.innerHeight),
                viewport_width: Math.floor(window.innerWidth),
                document_height: Math.floor(document.scrollingElement
                    ? document.scrollingElement.scrollHeight
                    : document.body.scrollHeight)
            })"""
        )

        walk_result, viewport_data = await asyncio.gather(walk_task, viewport_task)
    except PlaywrightError:  # pragma: no cover - defensive
        logger.warning("Failed to build annotated snapshot, using empty defaults")
        walk_result = {"content": "", "truncated": False}
        viewport_data = {
            "scroll_top": 0,
            "viewport_height": 800,
            "viewport_width": 1280,
            "document_height": 800,
        }

    return PageView(
        title=title,
        url=final_url,
        status_code=status_code,
        content=walk_result.get("content", ""),
        viewport=viewport_data,
        truncated=walk_result.get("truncated", False),
    )


__all__ = [
    "PageView",
    "build_page_view",
]
