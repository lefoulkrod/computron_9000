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
|  - Lifecycle      - DOM walker    - role:name   - Bezier     |
|  - ActiveView     - ARIA roles      resolution    mouse      |
|  - Interaction    - Viewport      - CSS/text    - Typing     |
|    cycle            clipping        fallbacks     delays     |
|  - Anti-bot       - Shadow DOM    - Fuzzy       - Scroll     |
|  - Frame detect   - Scoping         matching      timing    |
|                                                              |
|  Waits            Events          Exceptions    Selectors    |
|  (waits.py)       (events.py)     (exceptions   (selectors   |
|                                    .py)          .py)        |
|  - Network idle   - Progressive   - Unified     - CSS        |
|  - DOM quiet        screenshots     errors        generation |
|    window         - Throttling    - Context     - Vision     |
|                   - UI events       details       support    |
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
| `core/page_view.py` | `build_page_view()` — annotates the DOM with `[role] name` markers for the agent |
| `core/_selectors.py` | `_resolve_locator()` — maps `role:name` selectors from snapshots to Playwright locators |
| `core/selectors.py` | `SelectorRegistry` — generates unique CSS selectors for vision-grounded elements |
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

### 3. DOM Snapshots & Content Extraction (`core/page_view.py`)

Walks the DOM once per snapshot and produces LLM-consumable annotated text. The output uses `[role] name` inline annotations:

```
Welcome to our store
[link] Home  [link] Products  [link] Cart (3)
Search for products
[textbox] Search...
[button] Search
```

**The JavaScript walker** (`_ANNOTATED_SNAPSHOT_JS`) handles:

| Concern | How |
|---------|-----|
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

Converts `role:name` strings from annotated snapshots into Playwright Locators.

```
Agent sees:    [button] Add to Cart
Agent passes:  "button:Add to Cart"
                    |
                    v
            +-------------------+
            | _resolve_locator  |
            |                   |
            | 1. role:name      |  <-- Primary (from snapshot annotations)
            | 2. CSS selector   |  <-- Fallback (#id, [data-testid])
            | 3. Exact text     |  <-- get_by_text(exact=True)
            | 4. Substring text |  <-- get_by_text(exact=False)
            | 5. Alt text       |  <-- get_by_alt_text (for images)
            +--------+----------+
                     |
                     v
            Playwright Locator (scoped to frame)
```

**Features:**

- **Indexed selectors** — `button:Submit[2]` targets the 2nd visible "Submit" button.
- **Truncated names** — Names ending with `...` trigger fuzzy prefix matching.
- **Ambiguity handling** — Filters to viewport-visible elements; provides suggestions on mismatch.
- **`_LocatorResolution` dataclass** — Tracks which strategy won, match count, and resolved selector string.

---

### 5. CSS Selector Generation (`core/selectors.py`)

Generates unique CSS selectors for vision-grounded elements. Used by `vision.py` when the agent clicks by visual position and needs a stable selector.

**`SelectorRegistry`** tries strategies in cost order:

1. `#id`
2. `[data-testid]`, `[data-test]`, `[data-qa]`, `[data-cy]`
3. `[name]` (form fields)
4. ARIA role + label
5. Exact text match
6. Substring text
7. DOM position (`:nth-of-type()`)
8. Full DOM path
9. Fallback with `>> nth=0`

Each strategy is verified for uniqueness on the live page before acceptance.

---

### 6. Human-Like Simulation (`core/human.py`)

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

Formatted as: `[click] Element not found: button:Submit ({"selector": "button:Submit"})`

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
|  2. _resolve_locator(view.frame, selector)   |
|     -> Playwright Locator                    |
|                                              |
|  3. browser.perform_interaction(action_fn)   |
|     -> BrowserInteractionResult              |
|     (action + settle + change detection)     |
|                                              |
|  4. _build_snapshot(response)                |
|     -> PageView (if page changed)            |
|                                              |
|  5. Return InteractionResult                 |
|     (page_view, page_changed, reason, extras)|
|                                              |
|  6. @emit_screenshot_after    |
|     -> Screenshot event to UI (decorator)    |
+---------------------------------------------+
```

**Tools:**

| Function | What it does |
|----------|-------------|
| `click(selector)` | Resolves selector, human-clicks, returns snapshot if changed |
| `fill_field(selector, value)` | Validates input/textarea, clicks, clears, types with human timing |
| `press_keys(keys)` | Types key sequences with random delays, supports modifier chains |
| `scroll_page(direction, amount)` | Scrolls with budget enforcement per URL |
| `go_back()` | Browser back button |
| `drag(source, target, offset)` | Drag from element to element or by pixel offset |
| `press_and_hold(selector, duration)` | For bot-detection challenges (clamped 500-10000ms) |
| `click_at(x, y)` | Coordinate-based click |
| `press_and_hold_at(x, y, duration)` | Coordinate-based press-and-hold |

**`InteractionResult` model:** `page_view` (None if no change), `page_changed`, `reason`, `extras`

### Dropdown Selection (`select.py`)

Two-phase approach for `<select>` elements:

1. **Keyboard** (Home -> ArrowDown x N -> Enter) — generates `isTrusted: true` events that bypass JS validation.
2. **JS fallback** — Sets `selectedIndex` + dispatches change event.

### Read-Only Tools

| Tool | File | What it does |
|------|------|-------------|
| `browse_page(scope, full_page)` | `snapshot_tool.py` | Annotated `[role] name` snapshot, no side effects |
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

This provides a fallback path when DOM-based selectors can't find an element — the agent can "look" at the page and click by visual position.

### JavaScript Execution (`javascript.py`)

`execute_javascript(code, timeout_ms)` — Evaluates arbitrary JavaScript in the page context. Returns `JavaScriptResult` with `success`, `result`, and `error` fields.

---

## Events & Progressive Screenshots (`events.py`)

Streams browser screenshots to the UI without blocking tool execution.

```
+---------------------------------------------+
|        Progressive Screenshot Flow           |
|                                              |
|  Tool call in progress                       |
|       |                                      |
|       +-- request_progressive_screenshot()     |
|       |   (fire-and-forget)                  |
|       |        |                             |
|       |        v                             |
|       |   _ScreenshotEmitter (background task) |
|       |   - Coalesces rapid requests         |
|       |   - Min interval ~250ms (~4 fps)     |
|       |   - "Latest-value-only" drain        |
|       |   - Emits BrowserScreenshotPayload     |
|       |        |                             |
|       |        v                             |
|       |   UI receives screenshot event       |
|       |                                      |
|       +-- flush_progressive_screenshot()       |
|       |   (awaits in-flight capture)         |
|       |                                      |
|       +-- Tool returns result                |
|            |                                 |
|            v                                 |
|  @emit_screenshot_after       |
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
                        | tool call: click("button:Submit")
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
                    Locator
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
              InteractionResult
              (back to agent)
```

---

## Data Models

| Model | Type | Fields |
|-------|------|--------|
| `ActiveView` | NamedTuple | `frame`, `title`, `url` |
| `PageView` | Pydantic | `title`, `url`, `status_code`, `content`, `viewport`, `truncated` |
| `InteractionResult` | Pydantic | `page_view`, `page_changed`, `reason`, `extras` |
| `BrowserInteractionResult` | Pydantic | `navigation`, `page_changed`, `reason`, `navigation_response` |
| `GroundingResult` | Pydantic | `text`, `bbox`, `center`, `selector`, `reasoning` |
| `JavaScriptResult` | Pydantic | `success`, `result`, `error` |
| `SaveContentResult` | Pydantic | `filename`, `container_path`, `size_bytes` |
| `SelectorResult` | dataclass | `selector`, `strategy`, `collision_count`, `fallbacks_tried` |
| `_LocatorResolution` | dataclass | `locator`, `strategy`, `query`, `match_count`, `resolved_selector` |
