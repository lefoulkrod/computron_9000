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
from playwright.async_api import Response
from pydantic import BaseModel

from tools.browser.core._file_detection import DownloadInfo, is_file_content_type
from tools.browser.core.browser import ActiveView

# URL extensions that indicate non-HTML content the DOM walker can't handle.
_NON_HTML_EXTENSIONS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".ogg", ".webm",
    ".zip", ".gz", ".tar", ".bz2", ".xz", ".7z",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
})


def _is_non_html_url(url: str) -> bool:
    """Check if a URL points to a non-HTML resource based on its extension."""
    # Strip query string and fragment before checking extension
    path = url.split("?")[0].split("#")[0].lower()
    return any(path.endswith(ext) for ext in _NON_HTML_EXTENSIONS)

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = 8000
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
    viewport: dict[str, int] | None = None
    truncated: bool = False
    downloaded_file: DownloadInfo | None = None


# ---------------------------------------------------------------------------
# JavaScript DOM walker
# ---------------------------------------------------------------------------
# Executed via a single page.evaluate() call.  Accepts a params object:
#   { budget: number, scopeQuery: string | null, nameLimit: number,
#     fullPage: boolean }
# Returns: { content: string, truncated: boolean }

_ANNOTATED_SNAPSHOT_JS = """
(params) => {
  const { budget, scopeQuery, nameLimit, fullPage } = params;
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
    // inputs: label first (matches Playwright's accessible name), then placeholder, then value
    const tag = el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
      // Explicit label[for=id]
      const id = el.getAttribute('id');
      if (id) {
        const lbl = document.querySelector('label[for="' + id + '"]');
        if (lbl) return lbl.textContent.trim();
      }
      // Implicit wrapping label: <label>Text <input></label>
      const wrappingLabel = el.closest('label');
      if (wrappingLabel) {
        // Get only the label's own text, excluding the input's value/placeholder
        let labelText = '';
        for (const node of wrappingLabel.childNodes) {
          if (node.nodeType === 3) labelText += node.textContent;
          else if (node !== el && node.nodeType === 1 && !['INPUT','TEXTAREA','SELECT'].includes(node.tagName))
            labelText += (node.innerText || node.textContent || '');
        }
        labelText = labelText.trim();
        if (labelText) return labelText;
      }
      const ph = el.getAttribute('placeholder');
      if (ph) return ph.trim();
      // submit/button/reset inputs store their visible text in the value attribute
      if (tag === 'INPUT') {
        const val = el.getAttribute('value');
        if (val) return val.trim();
      }
    }
    // For <select> without a label, don't fall through to innerText —
    // innerText gives option text which doesn't match Playwright's
    // accessible name (ARIA spec only uses label/aria-label/aria-labelledby).
    if (tag === 'SELECT') return '';
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

  // ---- Inline text containers ----
  // Detects containers whose children are all inline/phrasing elements
  // with no interactive elements.  These should be emitted as a single
  // text chunk rather than recursed into — prevents fragmented output
  // when search engines wrap query terms in <b>/<strong> tags.
  const INLINE_TAGS = new Set([
    'B','STRONG','EM','I','U','S','SMALL','MARK','ABBR','CITE',
    'CODE','DFN','KBD','SAMP','VAR','SUB','SUP','SPAN','BDI','BDO',
    'DATA','TIME','Q','WBR','BR','DEL','INS','RUBY','RP','RT','FONT'
  ]);
  function isTextContainer(el) {
    if (el.shadowRoot) return false;  // Shadow DOM may contain interactive elements
    if (el.children.length === 0) return false;
    // Never collapse containers with interactive descendants — their
    // annotations would be lost.
    if (el.querySelector('a[href], button, input, select, textarea, [role]')) return false;
    for (const child of el.children) {
      if (!INLINE_TAGS.has(child.tagName)) return false;
    }
    return true;
  }

  // ---- Implicit interactivity ----
  // Detects elements that are clickable but lack proper ARIA roles.
  // Common in SPA widgets: <a> without href, <div> with cursor:pointer, etc.
  function isImplicitlyInteractive(el) {
    const tag = el.tagName;
    if (tag === 'BODY' || tag === 'HTML') return false;
    // Skip elements that contain proper interactive descendants — the
    // walker will annotate those children with their real roles instead.
    if (el.querySelector('a[href], button, input, select, textarea')) return false;
    if (el.shadowRoot && el.shadowRoot.querySelector('a[href], button, input, select, textarea')) return false;
    // tabindex makes an element explicitly focusable/clickable
    const ti = el.getAttribute('tabindex');
    if (ti !== null && ti !== '-1') return true;
    // cursor:pointer is the most common signal for custom interactive elements
    const s = window.getComputedStyle(el);
    if (s.cursor === 'pointer') {
      // Skip if cursor:pointer is inherited from parent — only detect
      // the element where cursor:pointer originates, not every child
      // that inherits it (prevents hundreds of false positives on sites
      // like Amazon where link/button children inherit cursor:pointer).
      const parent = el.parentElement;
      if (parent) {
        const ps = window.getComputedStyle(parent);
        if (ps.cursor === 'pointer') return false;
      }
      const text = (el.innerText || '').trim();
      if (text.length > 0 && text.length < 80) return true;
      // Accept image-only clickable elements (e.g. game cards, icon buttons)
      if (el.querySelector('img, svg, canvas')) return true;
    }
    return false;
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
    // Exempt modals/dialogs: role="dialog"|"alertdialog" (WAI-ARIA spec),
    // or large fixed overlays covering >50% of the viewport in both axes.
    if (scrolled && (s.position === 'sticky' || s.position === 'fixed')) {
      if (s.position === 'fixed') {
        const role = el.getAttribute('role');
        if (role === 'dialog' || role === 'alertdialog') return null;
        const r = el.getBoundingClientRect();
        if (r.width > vw * 0.5 && r.height > vh * 0.5) return null;
      }
      return 'skip-tree';
    }
    return null;
  }

  // Returns: 'visible' | 'clipped' | 'hidden'
  //   visible — element is in viewport and not clipped
  //   clipped — element is in viewport area but fully clipped by an
  //             overflow:hidden ancestor (e.g. CSS carousel panels).
  //             Children may still be visible so the walker should recurse.
  //   hidden  — element is entirely outside the viewport or zero-size
  function checkVisibility(el) {
    // In full-page mode, skip viewport clipping — walk all content
    if (fullPage) return 'visible';
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

  // Walk the child nodes of a container (element or shadow root).
  // Handles mixed content (text + element nodes) and <slot> elements
  // by walking their assignedNodes() to match rendered order.
  function walkChildren(container) {
    const hasMixed = container.childNodes.length > container.children.length;
    if (hasMixed) {
      for (const child of container.childNodes) {
        if (chars >= budget) break;
        if (child.nodeType === 3) {
          const text = child.textContent.trim();
          if (text.length > 1) emit(text);
        } else if (child.nodeType === 1) {
          walkSlotOrElement(child);
        }
      }
    } else {
      for (const child of container.children) {
        if (chars >= budget) break;
        walkSlotOrElement(child);
      }
    }
  }

  function walkSlotOrElement(el) {
    if (el.tagName === 'SLOT') {
      try {
        const assigned = el.assignedNodes();
        if (assigned.length > 0) {
          for (const node of assigned) {
            if (chars >= budget) break;
            if (node.nodeType === 3) {
              const text = node.textContent.trim();
              if (text.length > 1) emit(text);
            } else if (node.nodeType === 1) {
              walk(node, false);
            }
          }
        } else {
          // No assigned nodes — walk slot's default/fallback content
          walkChildren(el);
        }
      } catch (_e) { /* slot traversal failed — skip */ }
    } else {
      walk(el, false);
    }
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
      // Nameless comboboxes should still render (common on sites like
      // Amazon where <select> has no label/aria-label).
      if (!name && role !== 'combobox' && el.tagName !== 'SELECT') return;
      name = name ? truncName(name) : '';

      if (role === 'combobox' || el.tagName === 'SELECT') {
        const sel = el.querySelector('option:checked,option[selected]');
        const sv = sel ? sel.textContent.trim() : '';
        emit('[' + role + ']' + (name ? ' ' + name : '') + (sv ? ' = ' + sv : ''));
      } else if (role === 'checkbox' || role === 'radio' || role === 'switch') {
        const checked = el.checked || el.getAttribute('aria-checked') === 'true';
        emit('[' + role + '] ' + name + (checked ? ' (checked)' : ''));
      } else if (role === 'textbox' || role === 'searchbox' || role === 'spinbutton' || role === 'slider') {
        // Show current input value so the agent can verify fills worked
        const val = (el.value != null && el.value !== '') ? el.value : '';
        const display = val ? truncName(val) : '';
        emit('[' + role + '] ' + name + (display ? ' = ' + display : ''));
      } else {
        emit('[' + role + '] ' + name);
      }
      return;
    }

    // Detect clickable non-semantic elements (custom widgets, date pickers, etc.)
    // Also catches elements with non-interactive ARIA roles (e.g. gridcell,
    // cell, row, group) that are clickable via cursor:pointer — the
    // INTERACTIVE check above already returned for true widget roles.
    if (isImplicitlyInteractive(el)) {
      let name = (el.innerText || '').trim();
      // Fall back to child image alt text for image-only clickable elements
      if (!name || name.length >= 80) {
        const img = el.querySelector('img[alt]');
        if (img) name = (img.getAttribute('alt') || '').trim();
      }
      // Last resort: use data attributes or aria-label for identification
      if (!name) name = el.getAttribute('aria-label') || el.dataset.image || el.dataset.name || '';
      if (name && name.length < 80) {
        // Tag the element with ARIA attributes so Playwright's
        // get_by_role can locate it for click/interaction tools.
        el.setAttribute('role', 'button');
        el.setAttribute('aria-label', name);
        emit('[button] ' + truncName(name));
        return;
      }
    }

    // Headings
    if (role === 'heading') {
      const lvl = el.tagName.match(/H(\\d)/)?.[1] || '';
      const text = (el.innerText || '').trim();
      if (text) emit('[h' + lvl + '] ' + truncName(text));
      return;
    }

    // Images with alt text (or aria-label for div[role="img"])
    if (role === 'img') {
      const alt = (el.getAttribute('alt') || el.getAttribute('aria-label') || '').trim();
      if (alt) emit('[img] ' + truncName(alt));
      return;
    }

    // Leaf text node (no element children and no shadow root)
    if (el.children.length === 0 && !el.shadowRoot) {
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

    // Inline-only containers (e.g. <span> or <div> wrapping <b>/<em>/text):
    // collapse to a single text line.  Prevents fragmented output when
    // search engines highlight query terms with inline formatting tags.
    if (isTextContainer(el)) {
      const text = (el.innerText || '').trim();
      if (text && text.length > 1) {
        emit(text.length > 200 ? text.substring(0, 200) + '...' : text);
      }
      return;
    }

    // Recurse into children.
    // For shadow DOM hosts, walk the shadow tree (the rendered structure)
    // instead of light DOM children.  When a <slot> is encountered, walk
    // its assignedNodes() — these are the light DOM children projected
    // into that slot, rendered in the correct visual position.
    if (el.shadowRoot) {
      try { walkChildren(el.shadowRoot); }
      catch (_e) { /* Shadow DOM walk failed — fall back to light DOM */ walkChildren(el); }
    } else {
      walkChildren(el);
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
    view: ActiveView,
    response: Response | None,
    *,
    scope: str | None = None,
    budget: int = DEFAULT_BUDGET,
    full_page: bool = False,
) -> PageView:
    """Build an annotated snapshot combining content and interactive elements.

    Args:
        view: An ``ActiveView`` from ``Browser.active_view()``.
        response: Navigation response (may be ``None``).
        scope: Optional section name to scope to (matches headings/landmarks).
        budget: Character budget for the content field.

    Returns:
        ``PageView`` with annotated content, title, url, viewport info.
    """
    status_code = response.status if response is not None else None
    final_url = response.url if response is not None else view.url

    # Detect non-HTML content (PDF, images, etc.) before attempting JS evaluate
    # which would hang indefinitely on pages without a normal DOM.
    _non_html = False
    if response is not None:
        ct = getattr(response, "headers", {}).get("content-type", "")
        if ct and is_file_content_type(ct):
            _non_html = True
            logger.debug("Non-HTML content-type detected: %s", ct)
    if not _non_html and _is_non_html_url(view.url):
        _non_html = True
        logger.debug("Non-HTML URL extension detected: %s", view.url)

    if _non_html:
        # Determine file type from extension for a clearer message
        _ext = view.url.split("?")[0].rsplit(".", 1)[-1].lower() if "." in view.url else "file"
        walk_result = {
            "content": (
                f"[This is a {_ext.upper()} file, not a web page: {view.url}]\n"
                "The browser cannot display this content. Use go_back() to return "
                "to the previous page. If you need this file, download it with "
                "run_bash_cmd and curl/wget."
            ),
            "truncated": False,
        }
        viewport_data = None
    else:
        # Run JS DOM walk and viewport query in parallel on the active frame
        try:
            walk_task = view.frame.evaluate(
                _ANNOTATED_SNAPSHOT_JS,
                {"budget": budget, "scopeQuery": scope, "nameLimit": MAX_NAME_LEN, "fullPage": full_page},
            )

            viewport_task = view.frame.evaluate(
                """() => ({
                    scroll_top: Math.floor(window.scrollY),
                    viewport_height: Math.floor(window.innerHeight),
                    viewport_width: Math.floor(window.innerWidth),
                    document_height: Math.floor(document.scrollingElement
                        ? document.scrollingElement.scrollHeight
                        : document.body.scrollHeight)
                })"""
            )

            walk_result, viewport_data = await asyncio.wait_for(
                asyncio.gather(walk_task, viewport_task),
                timeout=15,
            )
        except asyncio.TimeoutError:
            logger.warning("DOM snapshot timed out for %s (may be non-HTML content)", view.url)
            walk_result = {
                "content": (
                    f"[Page content unavailable — snapshot timed out: {view.url}]\n"
                    "This may be a PDF or non-HTML document. Use go_back() to return "
                    "to the previous page. If you need this file, download it with "
                    "run_bash_cmd and curl/wget."
                ),
                "truncated": False,
            }
            viewport_data = None
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.warning("Failed to build annotated snapshot: %s", exc)
            walk_result = {"content": "", "truncated": False}
            viewport_data = None

    return PageView(
        title=view.title,
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
