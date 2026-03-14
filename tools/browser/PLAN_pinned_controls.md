# Plan: Pinned Controls in Site Filters

## Problem

When the LLM scrolls down on shopping/search sites, useful controls (search bar,
filters, sort options) leave the viewport and disappear from the page snapshot.
The LLM can still click them (Playwright operates on the full DOM), but it
doesn't know they exist anymore. This leads to unnecessary "scroll back to top"
round trips or the LLM forgetting it has filtering options.

## Insight

The JS DOM walker already walks the entire DOM and tags every node with its
viewport position (`in`, `clipped`, `out`). The Python pipeline then discards
`out` nodes in `_filter_viewport()`. The full node data is available — we just
throw it away before site filters see it.

## Design

Site filter plugins gain the ability to return **two node lists** instead of one:

- **Controls** — search bar, filter sidebar, sort buttons. Always shown at the
  top of the snapshot, outside the character budget.
- **Content** — product listings, article text, etc. Viewport-filtered and
  subject to the normal budget.

Sites without a plugin are completely unaffected — the generic pipeline stays
as-is.

### Example output after scrolling eBay

```
[Page: rtx 3090 | ebay.com/sch/... | 200]
[Viewport: 1500-2580 of 8000px]

[searchbox] Search for anything
[button] Search
[h3] Brand
[button] see all - Brand - opens dialog
[h3] Price
[link] Under $210.00
[link] $210.00 to $550.00
[link] Over $550.00
[h3] Condition
[link] New (2)
[link] Used (26)
[button] Sort (collapsed)

[link] GIGABYTE GeForce RTX 3090 GAMING OC 24GB...
$838.00 · 8 bids · 1d 17h left
[link] ASUS ROG Strix GeForce RTX 3090 OC...
$122.83 · 6 bids · 13h 42m left
...
```

## Changes

### 1. New type: `FilterResult` — `tools/browser/core/site_filters/__init__.py`

```python
class FilterResult(NamedTuple):
    controls: list[DomNode]  # Always shown, outside budget
    content: list[DomNode]   # Viewport-filtered, budget applies
```

Update `filter_for_site()` return type to `list[DomNode] | FilterResult`.
If a plugin returns a plain list, behavior is unchanged.

### 2. Pipeline change: `tools/browser/core/_pipeline.py`

Current order:
1. `parse_nodes()`
2. `_filter_viewport()` — drops `out` nodes
3. `_filter_scope()`
4. `filter_for_site()` — site plugin only sees viewport nodes
5. `_render_lines()` + `_apply_budget()`

New order:
1. `parse_nodes()` — full node list, all tagged with viewport position
2. `filter_for_site(url, all_nodes)` — site plugin gets **all** nodes
3. If plugin returned `FilterResult`:
   - `controls`: render directly (no viewport filter, no budget)
   - `content`: apply `_filter_viewport()` → `_filter_scope()` → `_render_lines()` → `_apply_budget()`
4. If plugin returned plain list (or no plugin matched):
   - `_filter_viewport()` → `_filter_scope()` → `_render_lines()` → `_apply_budget()` (unchanged)

The key change: site filters move **before** viewport filtering so they can
see the full DOM and pick out controls regardless of scroll position.

### 3. Update site plugins

Each plugin receives the full node list. Nodes still carry their `viewport`
field so the plugin can distinguish what's currently visible.

**`_ebay.py`** — `filter_ebay(nodes) -> FilterResult`:
- Controls: search combobox + Search button, sidebar filter headings/links
  (Brand, Price, Condition, Buying Format), Sort button
- Content: everything else (product listings, footer gets truncated as before)
- Phase 1 (strip nav) and Phase 3 (truncate footer) apply to content only

**`_amazon.py`** — `filter_amazon(nodes) -> FilterResult`:
- Controls: searchbox + Go button, sidebar filters (Price sliders, Customer
  Reviews, Delivery Day, Free Shipping)
- Content: everything else (product listings, noise filtering still applies)

### 4. No changes needed

- `format_page_view()` — unchanged, receives `content` as a single string
- `PageView` model — unchanged
- `build_page_view()` — unchanged, calls `process_snapshot()` as before
- JS DOM walker — unchanged, already walks full DOM
- All non-plugin sites — unchanged, same pipeline path

## How plugins identify controls

Each site plugin defines its own heuristic. For shopping sites, the pattern is
similar:

1. Walk nodes looking for the search bar (combobox/searchbox with "search" in
   the name) — grab it + the adjacent submit button
2. Walk nodes looking for the filter sidebar — typically a section starting with
   an `h2`/`h3` like "Filter" and containing links/checkboxes/sliders
3. Everything that's not controls is content

The plugin already knows the site structure (it's site-specific code), so this
is straightforward pattern matching on the same `DomNode` fields it already uses.

## Token cost

Filter controls for a typical shopping site are ~300-500 chars. On a 8000 char
budget, that's <6% overhead. The controls are only added for sites with plugins,
so most sites pay nothing.

## Testing

- Unit tests for `FilterResult` handling in `process_snapshot()`
- Unit tests per site plugin verifying controls vs content split
- Integration: open eBay/Amazon, scroll, verify controls persist in output
- Verify non-plugin sites are completely unaffected

## Verification

- `just test-file tests/tools/browser/core/test_pipeline.py`
- `just test` — full suite passes
