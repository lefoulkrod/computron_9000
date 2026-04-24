"""Page view combining content and interactive elements.

Walks the DOM in document order, emitting structured node data that the
Python pipeline transforms into the annotated text format the agent expects.
Each interactive element is stamped with a ``data-ct-ref`` attribute and
rendered as ``[ref] [role] name``.  Pass the ref number to ``click()``,
``fill_field()``, and other interaction tools.

Design goals:
    * Single ``page.evaluate()`` round-trip for the entire DOM walk
    * Viewport-clipped by default to keep output small
    * Ref numbers assigned in document order for deterministic selectors
    * Optional scoping to narrow output to a page section
    * Character budget enforced in Python pipeline
"""

from __future__ import annotations

import asyncio
import logging
import time

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Response
from pydantic import BaseModel

from tools.browser.core._file_detection import DownloadInfo, is_file_content_type
from tools.browser.core._pipeline import process_snapshot
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
    path = url.split("?")[0].split("#")[0].lower()
    return any(path.endswith(ext) for ext in _NON_HTML_EXTENSIONS)

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = 8000
MAX_NAME_LEN = 150


class PageView(BaseModel):
    """Page view combining content and interactive elements.

    Attributes:
        title: Page title.
        url: Final URL after any redirects.
        status_code: HTTP status code (``None`` if not from a navigation).
        content: Annotated text mixing content and ``[ref] [role] name`` annotations.
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
    # Snapshot timing (for logging, not serialized to LLM)
    snapshot_js_ms: float = 0
    snapshot_py_ms: float = 0
    snapshot_nodes: int = 0


# ---------------------------------------------------------------------------
# JavaScript structured DOM walker
# ---------------------------------------------------------------------------
# Executed via a single page.evaluate() call.  Accepts a params object:
#   { fullPage: boolean }
# Returns: { nodes: [...], viewport: { width, height, scroll_top, document_height } }
#
# Each interactive element is stamped with a data-ct-ref="N" attribute so
# Playwright locators can resolve refs via CSS attribute selectors.
#
# Emits structured node data — all formatting, scoping, deduplication,
# and budget enforcement happen in the Python pipeline (_pipeline.py).

_STRUCTURED_SNAPSHOT_JS = """
(params) => {
  const { fullPage } = params;
  const vh = window.innerHeight;
  const vw = window.innerWidth;

  // ---- Role mapping ----
  function getRole(el) {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    if (el.getAttribute('contenteditable') === 'true') return 'textbox';
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
          number:'spinbutton', range:'slider', checkbox:'checkbox',
          radio:'radio', submit:'button', reset:'button', button:'button'
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
    const al = el.getAttribute('aria-label');
    if (al) return al.trim();
    const lb = el.getAttribute('aria-labelledby');
    if (lb) {
      const ref = document.getElementById(lb);
      if (ref) return (ref.innerText || ref.textContent || '').trim();
    }
    const tag = el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
      const id = el.getAttribute('id');
      if (id) {
        const lbl = document.querySelector('label[for="' + id + '"]');
        if (lbl) return lbl.textContent.trim();
      }
      const wrappingLabel = el.closest('label');
      if (wrappingLabel) {
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
      if (tag === 'INPUT') {
        const val = el.getAttribute('value');
        if (val) return val.trim();
      }
    }
    if (tag === 'SELECT') return '';
    if (tag === 'IMG') return (el.getAttribute('alt') || '').trim();
    const t = el.innerText;
    return t ? t.trim() : '';
  }

  // ---- Inline text containers ----
  const INLINE_TAGS = new Set([
    'B','STRONG','EM','I','U','S','SMALL','MARK','ABBR','CITE',
    'CODE','DFN','KBD','SAMP','VAR','SUB','SUP','SPAN','BDI','BDO',
    'DATA','TIME','Q','WBR','BR','DEL','INS','RUBY','RP','RT','FONT'
  ]);
  function isTextContainer(el) {
    if (el.shadowRoot) return false;
    if (el.children.length === 0) return false;
    if (el.querySelector('a[href], button, input, select, textarea, [role]')) return false;
    for (const child of el.children) {
      if (!INLINE_TAGS.has(child.tagName)) return false;
    }
    return true;
  }

  // ---- Implicit interactivity ----
  function isImplicitlyInteractive(el) {
    const tag = el.tagName;
    if (tag === 'BODY' || tag === 'HTML') return false;
    if (el.querySelector('a[href], button, input, select, textarea')) return false;
    if (el.shadowRoot && el.shadowRoot.querySelector('a[href], button, input, select, textarea')) return false;
    const ti = el.getAttribute('tabindex');
    if (ti !== null && ti !== '-1') return true;
    const s = window.getComputedStyle(el);
    if (s.cursor === 'pointer') {
      const parent = el.parentElement;
      if (parent) {
        const ps = window.getComputedStyle(parent);
        if (ps.cursor === 'pointer') return false;
      }
      const text = (el.innerText || '').trim();
      if (text.length > 0 && text.length < 80) return true;
      if (el.querySelector('img, svg, canvas')) return true;
    }
    return false;
  }

  // ---- Visibility / viewport ----
  const scrolled = window.scrollY > 50;

  function shouldSkip(el) {
    if (el.getAttribute('aria-hidden') === 'true') {
      if (el.querySelector('[role="dialog"],[role="alertdialog"],dialog'))
        return 'skip-self';
      return 'skip-tree';
    }
    const s = window.getComputedStyle(el);
    if (s.display === 'none') return 'skip-tree';
    if (s.visibility === 'hidden') return 'skip-self';
    if (parseFloat(s.opacity) === 0
        && !(el.tagName === 'INPUT' && el.type === 'range'))
      return 'skip-self';
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

  function vpPos(el) {
    if (fullPage) return 'in';
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) {
      return (el.children.length > 0 || el.shadowRoot) ? 'clipped' : 'out';
    }
    if (!(r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw)) {
      if (el.children.length > 0 || el.shadowRoot) {
        const os = window.getComputedStyle(el);
        if (os.overflowY === 'visible' && el.scrollHeight > r.height + 1) {
          if (r.top + el.scrollHeight > 0 && r.top < vh) return 'clipped';
        }
        if (os.overflowX === 'visible' && el.scrollWidth > r.width + 1) {
          if (r.left + el.scrollWidth > 0 && r.left < vw) return 'clipped';
        }
      }
      return 'out';
    }
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
    return 'in';
  }

  const SKIP_ROLES = new Set(['separator']);

  // Structural container tags that emit container_start/container_end
  const CONTAINER_TAGS = new Set([
    'TABLE','THEAD','TBODY','TFOOT','TR','UL','OL','DL',
    'DETAILS','DIALOG','FIELDSET'
  ]);

  // ---- Ref counter ----
  let refCounter = 0;

  // Clean up stale refs from previous snapshots
  const stale = document.querySelectorAll('[data-ct-ref]');
  for (let i = 0; i < stale.length; i++) stale[i].removeAttribute('data-ct-ref');

  // ---- Output ----
  const nodes = [];
  let depth = 0;

  function emit(node) { nodes.push(node); }

  // Walk the child nodes of a container (element or shadow root).
  function walkChildren(container) {
    const hasMixed = container.childNodes.length > container.children.length;
    if (hasMixed) {
      for (const child of container.childNodes) {
        if (child.nodeType === 3) {
          const text = child.textContent.trim();
          if (text.length > 1) {
            emit({ type: 'text', depth: depth, text: text.length > 200 ? text.substring(0, 200) + '...' : text, viewport: 'in' });
          }
        } else if (child.nodeType === 1) {
          walkSlotOrElement(child);
        }
      }
    } else {
      for (const child of container.children) {
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
            if (node.nodeType === 3) {
              const text = node.textContent.trim();
              if (text.length > 1) {
                emit({ type: 'text', depth: depth, text: text.length > 200 ? text.substring(0, 200) + '...' : text, viewport: 'in' });
              }
            } else if (node.nodeType === 1) {
              walk(node, false);
            }
          }
        } else {
          walkChildren(el);
        }
      } catch (_e) { /* slot traversal failed */ }
    } else {
      walk(el, false);
    }
  }

  function walk(el, isRoot) {
    // Slot forwarding for double-nested shadow DOM (e.g. Reddit)
    if (el.tagName === 'SLOT') { walkSlotOrElement(el); return; }

    const skip = shouldSkip(el);
    if (skip === 'skip-tree') return;
    if (skip === 'skip-self') {
      for (const child of el.children) walk(child, false);
      return;
    }

    if (!isRoot) {
      const vis = vpPos(el);
      if (vis === 'out') return;
      if (vis === 'clipped') {
        for (const child of el.children) walk(child, false);
        return;
      }
    }

    const vp = isRoot ? 'in' : vpPos(el);
    const role = getRole(el);

    if (role && SKIP_ROLES.has(role)) return;

    // Interactive elements: stamp with ref, emit node data
    if (role && INTERACTIVE.has(role)) {
      let name = getName(el);
      if (!name && role !== 'combobox' && el.tagName !== 'SELECT') return;

      refCounter++;
      el.setAttribute('data-ct-ref', String(refCounter));

      const node = { type: 'interactive', depth: depth, ref: refCounter, role: role, name: name || '', viewport: vp };

      if (role === 'combobox' || el.tagName === 'SELECT') {
        const sel = el.querySelector('option:checked,option[selected]');
        // For <input role="combobox"> (autocomplete widgets), fall back to
        // el.value since child <option> elements won't exist.
        node.value = sel ? sel.textContent.trim()
                         : (el.value != null && el.value !== '') ? String(el.value) : '';
      } else if (role === 'checkbox' || role === 'radio' || role === 'switch') {
        node.checked = el.checked || el.getAttribute('aria-checked') === 'true';
      } else if (role === 'textbox' || role === 'searchbox' || role === 'spinbutton' || role === 'slider') {
        node.value = (el.value != null && el.value !== '') ? String(el.value) : '';
        if (role === 'slider') {
          node.extra = {
            min: parseFloat(el.min) || 0,
            max: parseFloat(el.max) || 100,
            width: Math.floor(el.getBoundingClientRect().width)
          };
        }
      }

      // ARIA state annotations
      const pressed = el.getAttribute('aria-pressed');
      if (pressed === 'true') node.pressed = true;
      const expanded = el.getAttribute('aria-expanded');
      if (expanded === 'true') node.expanded = true;
      else if (expanded === 'false') node.expanded = false;
      const selected = el.getAttribute('aria-selected');
      if (selected === 'true') node.selected = true;

      emit(node);
      return;
    }

    // Implicitly interactive elements (cursor:pointer, tabindex, etc.)
    if (isImplicitlyInteractive(el)) {
      let name = (el.innerText || '').trim();
      if (!name || name.length >= 80) {
        const img = el.querySelector('img[alt]');
        if (img) name = (img.getAttribute('alt') || '').trim();
      }
      if (!name) name = el.getAttribute('aria-label') || el.dataset?.image || el.dataset?.name || '';
      if (name && name.length < 80) {
        refCounter++;
        el.setAttribute('data-ct-ref', String(refCounter));
        el.setAttribute('role', 'button');
        el.setAttribute('aria-label', name);
        emit({ type: 'interactive', depth: depth, ref: refCounter, role: 'button', name: name, viewport: vp });
        return;
      }
    }

    // Headings
    if (role === 'heading') {
      const lvl = el.tagName.match(/H(\\d)/)?.[1] || '';
      const text = (el.innerText || '').trim();
      if (text) emit({ type: 'heading', depth: depth, name: text, level: parseInt(lvl) || null, viewport: vp });
      return;
    }

    // Images
    if (role === 'img') {
      const alt = (el.getAttribute('alt') || el.getAttribute('aria-label') || '').trim();
      if (alt) emit({ type: 'image', depth: depth, name: alt, viewport: vp });
      return;
    }

    // Structural containers
    if (CONTAINER_TAGS.has(el.tagName)) {
      emit({ type: 'container_start', depth: depth, tag: el.tagName.toLowerCase(), viewport: vp });
      depth++;
      walkChildren(el);
      depth--;
      emit({ type: 'container_end', depth: depth, tag: el.tagName.toLowerCase(), viewport: vp });
      return;
    }

    // Leaf text node
    if (el.children.length === 0 && !el.shadowRoot) {
      const text = (el.innerText || '').trim();
      if (text && text.length > 1) {
        emit({ type: 'text', depth: depth, text: text.length > 200 ? text.substring(0, 200) + '...' : text, viewport: vp });
      }
      return;
    }

    // Paragraph-like containers
    if (el.tagName === 'P' || el.tagName === 'BLOCKQUOTE' || el.tagName === 'FIGCAPTION') {
      // Check for interactive children first — if present, recurse normally
      if (el.querySelector('a[href], button, input, select, textarea, [role]')) {
        walkChildren(el);
        return;
      }
      const text = (el.innerText || '').trim();
      if (text && text.length > 1) {
        emit({ type: 'text', depth: depth, text: text.length > 200 ? text.substring(0, 200) + '...' : text, viewport: vp });
      }
      return;
    }

    // Inline-only containers
    if (isTextContainer(el)) {
      const text = (el.innerText || '').trim();
      if (text && text.length > 1) {
        emit({ type: 'text', depth: depth, text: text.length > 200 ? text.substring(0, 200) + '...' : text, viewport: vp });
      }
      return;
    }

    // Recurse into children / shadow DOM
    if (el.shadowRoot) {
      try { walkChildren(el.shadowRoot); }
      catch (_e) { walkChildren(el); }
    } else {
      walkChildren(el);
    }
  }

  walk(document.body, true);

  return {
    nodes: nodes,
    viewport: {
      width: Math.floor(vw),
      height: Math.floor(vh),
      scroll_top: Math.floor(window.scrollY),
      document_height: Math.floor(
        document.scrollingElement
          ? document.scrollingElement.scrollHeight
          : document.body.scrollHeight
      )
    }
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
        full_page: When True, include off-screen nodes in the snapshot.

    Returns:
        ``PageView`` with annotated content, title, url, viewport info.
    """
    status_code = response.status if response is not None else None
    final_url = response.url if response is not None else view.url
    snapshot_js_ms = 0.0
    snapshot_py_ms = 0.0
    snapshot_nodes = 0

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

    content = ""
    truncated = False
    viewport_data: dict[str, int] | None = None

    if _non_html:
        _ext = view.url.split("?")[0].rsplit(".", 1)[-1].lower() if "." in view.url else "file"
        content = (
            f"[This is a {_ext.upper()} file, not a web page: {view.url}]\n"
            "The browser cannot display this content. Use go_back() to return "
            "to the previous page. If you need this file, download it with "
            "run_bash_cmd and curl/wget."
        )
    else:
        try:
            t0 = time.monotonic()
            raw_result = await asyncio.wait_for(
                view.frame.evaluate(
                    _STRUCTURED_SNAPSHOT_JS,
                    {"fullPage": full_page},
                ),
                timeout=15,
            )
            t_js = time.monotonic()

            raw_nodes = raw_result.get("nodes", [])
            raw_viewport = raw_result.get("viewport", {})

            viewport_data = {
                "scroll_top": raw_viewport.get("scroll_top", 0),
                "viewport_height": raw_viewport.get("height", 800),
                "viewport_width": raw_viewport.get("width", 1280),
                "document_height": raw_viewport.get("document_height", 0),
            }

            content, truncated = process_snapshot(
                raw_nodes,
                url=view.url,
                scope_query=scope,
                budget=budget,
                name_limit=MAX_NAME_LEN,
                full_page=full_page,
            )
            t_py = time.monotonic()

            snapshot_js_ms = (t_js - t0) * 1000
            snapshot_py_ms = (t_py - t_js) * 1000
            snapshot_nodes = len(raw_nodes)
        except TimeoutError:
            logger.warning("DOM snapshot timed out for %s (may be non-HTML content)", view.url)
            content = (
                f"[Page content unavailable — snapshot timed out: {view.url}]\n"
                "This may be a PDF or non-HTML document. Use go_back() to return "
                "to the previous page. If you need this file, download it with "
                "run_bash_cmd and curl/wget."
            )
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.warning("Failed to build annotated snapshot: %s", exc)

    return PageView(
        title=view.title,
        url=final_url,
        status_code=status_code,
        content=content,
        viewport=viewport_data,
        truncated=truncated,
        snapshot_js_ms=snapshot_js_ms,
        snapshot_py_ms=snapshot_py_ms,
        snapshot_nodes=snapshot_nodes,
    )


__all__ = [
    "PageView",
    "build_page_view",
]
