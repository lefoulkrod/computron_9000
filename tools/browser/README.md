# Browser Tools

Browser automation tools powered by Playwright. These tools are used by the browser agent to navigate, read, and interact with web pages.

## Architecture Overview

```
+-------------------------------------------------------------+
|                      TOOL LAYER (Public API)                 |
|                                                              |
|  open_url  browse_page  click  fill_field  scroll_page ...   |
|  page.py   snapshot_    interactions.py    select.py         |
|            tool.py      read_content.py    vision.py         |
|                         javascript.py      save_content.py   |
+-----------------------------+--------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                    CORE LAYER (Internals)                     |
|                                                              |
|  Browser          PageView        Selectors     Human        |
|  (browser.py)     (page_view.py)  (_selectors   (human.py)   |
|                                    .py)                      |
|  - Lifecycle      - DOM walker    - Ref-based   - Bezier     |
|  - ActiveView     - ARIA roles      resolution    mouse      |
|  - Interaction    - Viewport      - CSS         - Typing     |
|    cycle            clipping        fallback      delays     |
|  - Anti-bot       - Shadow DOM                  - Scroll     |
|  - Frame detect   - Scoping                       timing    |
|                   - Ref stamping                             |
|                                                              |
|  Waits            Events          Exceptions                 |
|  (waits.py)       (events.py)     (exceptions.py)            |
|                                                              |
|  - Network idle   - Progressive   - Unified errors           |
|  - DOM quiet        screenshots   - Context details          |
|    window         - Throttling                               |
|                   - UI events                                |
+-----------------------------+--------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                    PLAYWRIGHT (External)                      |
|                                                              |
|  Persistent Context -> Pages -> Frames -> Locators -> Actions|
+-------------------------------------------------------------+
```

## Module Structure

| File | Purpose |
|------|---------|
| `core/browser.py` | Singleton `Browser` class — manages Playwright lifecycle, page tracking, and the settle/interaction cycle |
| `core/page_view.py` | `build_page_view()` — walks the DOM producing `[ref] [role] name` annotated text, stamps `data-ct-ref` attributes |
| `core/_selectors.py` | `_resolve_locator()` — resolves ref numbers to Playwright locators via `[data-ct-ref="N"]` |
| `core/_dom_nodes.py` | `DomNode` dataclass and `parse_nodes()` for structured DOM node data |
| `core/_pipeline.py` | Rendering pipeline — converts `DomNode` list to formatted text output |
| `core/human.py` | Human-like mouse movement, click hold, and keystroke timing |
| `core/waits.py` | Navigation detection and DOM settle logic |
| `core/exceptions.py` | `BrowserToolError` base exception |
| `interactions.py` | `click()`, `fill_field()`, `press_keys()`, `scroll_page()`, `drag()`, `go_back()` |
| `snapshot_tool.py` | `browse_page()` — reads the current page without side effects |
| `read_content.py` | `read_page()` — reads the current page as clean markdown text |
| `page.py` | `open_url()` — navigates to a URL |
| `select.py` | `select_option()` — dropdown/combobox interactions |
| `javascript.py` | `execute_javascript()` — raw JS evaluation |
| `vision.py` | `ask_about_screenshot()`, `ground_elements_by_text()` — screenshot analysis via vision model |
| `save_content.py` | `save_page_content()` — saves page HTML as markdown |
| `events.py` | Emits progressive browser screenshot events to the UI |

---

## Core Responsibilities

### 1. Browser Lifecycle & State (`core/browser.py`)

Manages a **persistent Playwright browser singleton**. A single browser instance lives for the entire process, preserving cookies, localStorage, and session state across tool calls.

**Key types:**

- **`Browser`** — Wraps a persistent Playwright context. Handles page creation, navigation, and the interaction cycle.
- **`ActiveView`** — `NamedTuple(frame, title, url)` — The canonical "where to interact" abstraction. Can point at the main page or a dominant iframe.
- **`get_browser()`** — Lazily initializes the singleton.
- **`close_browser()`** — Tears down and clears the singleton.

**Page management:**

- `current_page()` — Returns the most recent non-closed page or creates a new one.
- `new_page()` — Opens a new page with jittered viewport dimensions.
- `pages()` — Lists all open pages.

**Anti-bot defenses** (injected via `add_init_script`):

| Patch | What it does |
|-------|-------------|
| `navigator.webdriver` | Set to `false` |
| `navigator.languages` / `platform` | Spoofed to realistic values |
| `window.chrome.runtime` | Faked as a real object |
| `navigator.plugins` | Proxy wrapping real PluginArray |
| WebGL vendor/renderer | Spoofed to Intel |
| Permissions API | Returns `"prompt"` for notifications |
| `outerWidth` / `outerHeight` | Matched to screen bounds |
| `navigator.userAgentData.brands` | Includes "Google Chrome" |
| `attachShadow` | Forced to `mode: 'open'` so DOM walker sees shadow roots |
| Page-change detection | Listeners for beforeunload, pushState, replaceState, popstate, MutationObserver |

---

### 2. The Interaction Cycle (`Browser.perform_interaction`)

Every interaction tool (click, fill, scroll, etc.) delegates to `perform_interaction()`. This is the heart of the system:

```
+----------------------------------------------------+
|          perform_interaction(action_fn)              |
|                                                     |
|  1. Reset     - Clear __pageChange__ markers        |
|  2. Execute   - Call action_fn (click, type, etc.)  |
|  3. Flush     - Await in-flight progressive snap    |
|  4. Detect    - Read __pageChange__ flags           |
|  5. Settle    - Wait for network idle + DOM quiet   |
|  6. Re-check  - Read flags again (async updates)    |
|  7. Classify  - browser-nav / history-nav /         |
|                  dom-mutation / no-change            |
|  8. Frame     - Re-detect dominant iframe           |
|  9. Delay     - 300-800ms human reading pause       |
+----------------------------------------------------+
```

**Change classification:**

| Reason | Trigger |
|--------|---------|
| `browser-navigation` | Hard page reload detected |
| `history-navigation` | pushState / replaceState / popstate |
| `dom-mutation` | DOM changed without navigation |
| `no-change` | No detectable changes |

---

### 3. DOM Snapshots & Ref Stamping (`core/page_view.py`)

Walks the DOM once per snapshot and produces LLM-consumable annotated text. Each interactive element is stamped with a `data-ct-ref` attribute and shown with a `[ref] [role] name` annotation:

```
Welcome to our store
[1] [link] Home  [2] [link] Products  [3] [link] Cart (3)
Search for products
[4] [textbox] Search...
[5] [button] Search
```

The agent uses the ref number as the selector for interaction tools: `click("5")`, `fill_field("4", "laptop")`.

**The JavaScript walker** (`_ANNOTATED_SNAPSHOT_JS`) handles:

| Concern | How |
|---------|-----|
| Ref stamping | Assigns sequential `data-ct-ref` attributes to each interactive element |
| Stale cleanup | Removes old `data-ct-ref` attributes before each snapshot |
| Role mapping | HTML tag -> ARIA role (A->link, BUTTON->button, INPUT[type]->specific role) |
| Accessible name | aria-label -> aria-labelledby -> label[for] -> placeholder -> alt -> innerText |
| Visibility | Skips aria-hidden, display:none, opacity:0, overflow-clipped elements |
| Viewport clipping | Only emits visible elements (unless `full_page=True`) |
| Shadow DOM | Traverses `el.shadowRoot` after light DOM children |
| Scoping | Narrows to heading/landmark matching query text |
| Budget | Default 8000 char limit with truncation flag |
| Dedup | Tracks emitted lines to avoid repetition |
| Form state | Shows combobox selected value, checkbox checked state, textbox current value |

**`PageView` model** (Pydantic): `title`, `url`, `status_code`, `content`, `viewport`, `truncated`

---

### 4. Selector Resolution (`core/_selectors.py`)

Resolves ref numbers from annotated page views into Playwright Locators using `data-ct-ref` attribute selectors.

```
Agent sees:    [5] [button] Add to Cart
Agent passes:  "5"
                    |
                    v
            +-------------------+
            | _resolve_locator  |
            |                   |
            | 1. Parse as int   |
            | 2. Lookup via     |
            |    [data-ct-ref]  |
            | 3. CSS fallback   |  <-- Non-numeric strings tried as CSS
            +--------+----------+
                     |
                     v
            Playwright Locator (scoped to frame)
```

**How it works:**

- **Ref lookup** — Numeric strings (e.g. `"5"`) resolve via `page.locator('[data-ct-ref="5"]')`. This is 100% reliable because the walker stamps each element during the snapshot.
- **CSS fallback** — Non-numeric strings are tried as CSS selectors for backwards compatibility.
- **Stale refs** — If a ref is not found (page changed since snapshot), a `BrowserToolError` tells the agent to call `browse_page()` for fresh refs.
- **`_LocatorResolution` dataclass** — `locator`, `query`, `resolved_selector`.

---

### 5. Human-Like Simulation (`core/human.py`)

Makes browser interactions look human to anti-bot systems.

**Mouse movement:**

```
human_click(frame, locator)
    |
    +-- Get element bounding box
    +-- Build Bezier trajectory (cubic curve with control points)
    +-- Apply ease-in-out timing (sinusoidal)
    +-- Move mouse along path in N steps
    +-- Hover (50-200ms random)
    +-- Click (hold 50-150ms random)
```

**Typing:**

```
human_type(frame, locator, text)
    |
    +-- Click to focus
    +-- Clear existing text (Ctrl+A -> Backspace)
    +-- Type each character with:
        +-- Random delay (30-90ms per key)
        +-- Extra pause every N chars (100-300ms)
```

**`_page_for(target: Page | Frame) -> Page`** — Utility that extracts the Page from a Page or Frame, since mouse/keyboard APIs require Page-level access.

All timing parameters are configurable via `config.yaml` under `tools.browser.human`.

---

### 7. Post-Interaction Settling (`core/waits.py`)

Waits for the page to stabilize after an interaction.

- **Navigation settle** — Waits for `networkidle` load state (configurable timeout).
- **DOM settle** — JavaScript watches for N ms of no MutationObserver activity (ignores input value changes). Respects a max timeout to avoid hanging on constantly-mutating pages.

---

### 8. Error Handling (`core/exceptions.py`)

All browser tool failures raise `BrowserToolError` with:

- `message` — Human-readable description
- `tool` — Short identifier (e.g. `"click"`, `"fill_field"`)
- `details` — Optional JSON-serializable context dict

Formatted as: `[click] Ref 5 not found on the page. ({"selector": "[data-ct-ref=\"5\"]"})`

---

## Tool Implementations

### Interaction Tools (`interactions.py`)

Every interaction tool follows the same pattern:

```
+---------------------------------------------+
|           Standard Tool Flow                 |
|                                              |
|  1. get_active_view("tool_name")             |
|     -> (Browser, ActiveView)                 |
|                                              |
|  2. _resolve_or_raise(view.frame, selector)  |
|     -> _LocatorResolution                    |
|     (ref number -> [data-ct-ref] locator)    |
|                                              |
|  3. browser.perform_interaction(action_fn)   |
|     -> BrowserInteractionResult              |
|     (action + settle + change detection)     |
|                                              |
|  4. _format_result(browser_result)           |
|     -> Formatted string with page snapshot   |
|                                              |
|  5. @emit_screenshot_after                   |
|     -> Screenshot event to UI (decorator)    |
+---------------------------------------------+
```

**Tools:**

| Function | What it does |
|----------|-------------|
| `click(selector)` | Resolves ref, human-clicks, returns snapshot |
| `fill_field(selector, value)` | Validates input/textarea, clicks, clears, types with human timing |
| `press_keys(keys)` | Types key sequences with random delays, supports modifier chains |
| `scroll_page(direction, amount)` | Scrolls with budget enforcement per URL |
| `go_back()` | Browser back button |
| `drag(source, target, offset)` | Drag from element to element or by pixel offset |
| `press_and_hold(selector, duration)` | For bot-detection challenges (clamped 500-10000ms) |
| `click_at(x, y)` | Coordinate-based click |
| `press_and_hold_at(x, y, duration)` | Coordinate-based press-and-hold |

All interaction tools return a formatted string containing the action header and updated page snapshot.

### Dropdown Selection (`select.py`)

Two-phase approach for `<select>` elements:

1. **Keyboard** (Home -> ArrowDown x N -> Enter) — generates `isTrusted: true` events that bypass JS validation.
2. **JS fallback** — Sets `selectedIndex` + dispatches change event.

### Read-Only Tools

| Tool | File | What it does |
|------|------|-------------|
| `browse_page(scope, full_page)` | `snapshot_tool.py` | Annotated `[ref] [role] name` snapshot, no side effects |
| `open_url(url)` | `page.py` | Navigates + returns snapshot with status_code |
| `read_page(page_number, query)` | `read_content.py` | Full markdown via html2text, 20K char pagination, optional query filtering |
| `save_page_content(filename)` | `save_content.py` | Saves page as markdown file |

### Vision Tools (`vision.py`)

Screenshot-based analysis using a vision model (Ollama).

```
ask_about_screenshot(prompt, mode)
    |
    +-- Capture screenshot (full_page / viewport / element)
    +-- Send to vision model with prompt
    +-- Return textual response

ground_elements_by_text(text)
    |
    +-- Capture screenshot
    +-- Ask vision model for element locations
    +-- Parse normalized 0-1000 bounding boxes
    +-- Resolve CSS selectors from page
    +-- Return list[GroundingResult]
            |
            +-- click_element(grounding_result)
                    +-- click_at(center_x, center_y)
```

This provides a fallback path when ref-based selectors can't find an element — the agent can "look" at the page and click by visual position.

### JavaScript Execution (`javascript.py`)

`execute_javascript(code, timeout_ms)` — Evaluates arbitrary JavaScript in the page context. Returns a dict with `success`, `result`, and `error` fields.

---

## Events & Progressive Screenshots (`events.py`)

Streams browser screenshots to the UI without blocking tool execution.

```
+---------------------------------------------+
|        Progressive Screenshot Flow           |
|                                              |
|  Tool call in progress                       |
|       |                                      |
|       +-- request_progressive_screenshot()   |
|       |   (fire-and-forget)                  |
|       |        |                             |
|       |        v                             |
|       |   _ScreenshotEmitter (background)    |
|       |   - Coalesces rapid requests         |
|       |   - Min interval ~250ms (~4 fps)     |
|       |   - "Latest-value-only" drain        |
|       |   - Emits BrowserScreenshotPayload   |
|       |        |                             |
|       |        v                             |
|       |   UI receives screenshot event       |
|       |                                      |
|       +-- flush_progressive_screenshot()     |
|       |   (awaits in-flight capture)         |
|       |                                      |
|       +-- Tool returns result                |
|            |                                 |
|            v                                 |
|  @emit_screenshot_after                      |
|  (decorator captures final screenshot)       |
+---------------------------------------------+
```

Screenshots are emitted to the UI for visual feedback but are **not included in tool return values** — this saves LLM context tokens.

---

## Active Frame (iframe support)

When a dominant iframe covers >25% of the viewport (e.g. booking widgets, modal overlays), all tools automatically operate on that iframe instead of the main page. This is transparent to the agent — it doesn't need to know about iframes.

- `Browser.active_frame()` — Returns dominant iframe if detected, else main page.
- `Browser._detect_dominant_frame()` — Measures iframe bounding boxes, skips detached frames.
- `Browser.clear_active_frame()` — Resets to main page.
- `Browser.active_view()` — Proactively detects dominant iframe, returns `ActiveView`.

---

## Scroll Budget

Prevents the agent from scrolling endlessly on long pages. Tracked **per URL, per async task** (using `contextvars` so concurrent requests don't interfere).

- **Warn threshold**: After N scrolls on the same URL, a warning is injected into the snapshot telling the agent to stop or use `browse_page(full_page=True)`.
- **Hard limit**: After N scrolls, `scroll_page()` raises `BrowserToolError` and refuses to scroll further.
- **URL change resets**: Navigating to a new page resets the counter.

### Configuration (`config.yaml`)

```yaml
tools:
  browser:
    scroll_warn_threshold: 5   # scrolls before warning appears
    scroll_hard_limit: 10      # scrolls before hard stop
```

---

## Cross-Cutting Interaction Map

```
                    Agent (LLM)
                        |
                        | tool call: click("5")
                        v
              +------------------+
              |  interactions.py  |
              +---------+--------+
                        |
          +-------------+-------------+
          v             v             v
   get_active_view  _resolve     perform_
   (browser.py)     _locator     interaction
          |        (_selectors   (browser.py)
          |         .py)              |
          v             |     +-------+-------+
    Browser.            |     |       |       |
    active_view()       |   human_  waits.  page_change
          |             |   click() py     detection JS
          |             |   (human         (browser.py)
          v             |    .py)
    ActiveView          |
    (frame,title,url)   |
                        v
              [data-ct-ref="5"]
                        |
                        v
              +-----------------+
              | Playwright API  |
              +--------+--------+
                       |
                       v
              +-----------------+     +--------------+
              |  DOM changes    |---->| events.py    |
              +-----------------+     | (screenshot  |
                       |              |  to UI)      |
                       v              +--------------+
              build_page_view()
              (page_view.py)
                       |
                       v
              Formatted string
              (back to agent)
```

---

## Data Models

| Model | Type | Fields |
|-------|------|--------|
| `ActiveView` | NamedTuple | `frame`, `title`, `url` |
| `PageView` | Pydantic | `title`, `url`, `status_code`, `content`, `viewport`, `truncated` |
| `DomNode` | dataclass | `type`, `text`, `role`, `name`, `ref`, `value`, `checked`, `viewport` |
| `BrowserInteractionResult` | Pydantic | `navigation`, `page_changed`, `reason`, `navigation_response` |
| `GroundingResult` | Pydantic | `text`, `bbox`, `center`, `selector`, `reasoning` |
| `_LocatorResolution` | dataclass | `locator`, `query`, `resolved_selector` |
