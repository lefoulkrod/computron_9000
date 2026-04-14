# UI Architecture

## Conceptual Framework

The UI is built around two core concepts:

- **Chat View** — A multi-turn conversation between the user and the root agent. Messages accumulate as a scrollable thread. Always mounted (hidden via CSS when other views are active to preserve scroll and input state).
- **Activity View** — A real-time log of a single agent's work: thinking, content, tool calls, file outputs. Shown when drilling into an agent from the network graph.

Both views share a **tabbed preview panel** on the right side for browser screenshots, terminal output, file previews, desktop VNC, and media generation.

---

## Layout

The UI uses a fixed app shell with a split main area:

```
┌──────┬─────────────────────────────┬───┬──────────────────┐
│      │                             │   │  [tabs]          │
│ Side │  Main View                  │ ┃ │  Browser         │
│ bar  │  (Chat / Activity /         │ ┃ │  file.py    x    │
│      │   Network / Goals /         │ ┃ │  Terminal        │
│      │   Settings)                 │ ┃ │                  │
│      │                             │ ┃ │  Preview content │
│      │                             │   │                  │
└──────┴─────────────────────────────┴───┴──────────────────┘
         left side                    ^     right side
                                  drag handle
```

### App Shell

- **Header** (36px) — Logo, app title ("COMPUTRON_9000" in monospace), audio indicator, desktop button, theme toggle, new conversation. Fixed top.
- **Sidebar** (44px) — Vertical icon buttons: Chat, Agents, Goals, Memory | Conversations, Tools | Settings. Active item has a 2px accent bar on the left edge (Signal Line). Fixed left.
- **Flyout panels** (270px) — Slide out from the sidebar for Memory, Conversations, and Custom Tools. Overlay with scrim.

### Main Area Views

The left side shows one of these (mutually exclusive):

| View | Trigger | Width | Preview panel visible? |
|------|---------|-------|----------------------|
| **Chat** | Default / Chat sidebar button | Shares with preview | Yes |
| **Agent Activity** | Click agent in network graph | Shares with preview | Yes |
| **Network Graph** | Agents sidebar button | Full width | No |
| **Goals** | Goals sidebar button | Full width | No |
| **Settings** | Settings sidebar button | Full width | No |

The preview panel is a shared tabbed panel on the right. It's visible alongside Chat and Activity views, hidden for full-width views (Network, Goals, Settings). A draggable divider between the main view and preview panel allows resizing (20-80% range).

### Mobile

On viewports <= 768px, the app switches to a single-column layout: header, scrollable message area, bottom input bar. No sidebar, no preview panels, no agent views. A drawer provides access to settings and conversations.

---

## State Architecture

### Agent Reducer (source of truth for agent & preview data)

All agent and preview data lives in a single reducer (`useAgentState`). Each agent node holds its own state:

```
agents: {
  [agentId]: {
    activityLog[]        // thinking, content, tool calls, file outputs
    browserSnapshot      // latest screenshot + URL + title
    terminalLines[]      // command history (append-only)
    desktopActive        // VNC session flag
    generationPreview    // image/video/audio generation state
    openFiles[]          // files opened in preview tabs
    status               // running | success | error | stopped
    iteration            // current loop iteration
    contextUsage         // { context_used, context_limit, fill_ratio }
  }
}
selectedAgentId          // which agent is drilled into (or null)
```

### Preview State Hook (`usePreviewState`)

Derives all preview panel state from the agent reducer:

- Computes tab list from the active agent's data (browser, terminal, files, etc.)
- Manages which tab is selected, split position, fullscreen state
- Determines which agent's previews to show: selected sub-agent if one is drilled in, otherwise the root agent

### Chat State (`useStreamingChat`)

Manages the conversation thread separately:

- `messages[]` — User and assistant messages for the root agent
- `isStreaming` — Whether a response is in flight
- `sendMessage()`, `stopGeneration()`, `loadConversation()`, `newConversation()`

### Event Flow

```
Backend SSE stream (/api/chat)
    │
    ├── depth == 0 (root agent tokens)
    │   └── Buffer → requestAnimationFrame → setMessages()
    │       → Chat View renders
    │
    └── depth > 0 (sub-agent tokens)
        └── Buffer → requestAnimationFrame → agentDispatch(APPEND_STREAM_CHUNK)
            → Activity View renders
```

Preview events (screenshots, terminal output, desktop, generation) dispatch directly to the agent reducer via stable `useRef` callbacks. The preview hook reads from the reducer and computes tabs automatically.

Agent lifecycle events (`agent_started`, `agent_completed`) update the agent tree. New root agents carry over preview state (browser, terminal, desktop, generation) from the previous root.

---

## Component Tree

```
AgentStateProvider
└── DesktopAppInner
    ├── Header
    ├── Sidebar
    ├── FlyoutPanel?  (Memory | Conversations | CustomTools)
    │
    ├── mainContent
    │   ├── SettingsPage                         (full-width)
    │   ├── GoalsView                            (full-width, split-panel)
    │   ├── AgentNetwork                         (full-width)
    │   ├── AgentActivityView                    (left column)
    │   │   └── AgentOutput → FileOutput
    │   ├── ChatPanel                            (left column, always mounted)
    │   │   ├── ChatMessages → Message → AgentOutput → FileOutput
    │   │   ├── StarterPrompts                   (shown when empty)
    │   │   └── ChatInput
    │   │
    │   ├── SplitHandle                          (draggable divider)
    │   └── PreviewPanel                         (right column, shared)
    │       ├── [tab bar]
    │       ├── BrowserPreview
    │       ├── FilePreviewInline → FileContentRenderer
    │       ├── TerminalPanel
    │       ├── DesktopPreview
    │       └── GenerationPreview
    │
    ├── FullscreenPreview                        (viewport overlay for files)
    └── SetupWizard                              (shown if setup incomplete)
```

### Key Shared Components

| Component | Where used | Notes |
|---|---|---|
| **AgentOutput** | Chat messages + Activity view | Ordered list of entries (thinking, content, tool calls, files) |
| **CollapsibleThinking** | Both views | `compact` prop for smaller text in activity view |
| **FileOutput** | Both views | Click "Preview" opens file in the shared preview panel |
| **ContextUsageBadge** | Chat header + Agent header | SVG donut showing context fill percentage |
| **PreviewShell** | All preview panels | Wraps content with title bar, collapse/expand/close buttons |

### File Preview Flow

```
FileOutput (in chat/activity stream)
    │ click "Preview"
    ▼
usePreviewState.openFile(item)
    │ dispatches OPEN_FILE to reducer
    ▼
PreviewPanel tab appears
    │
    ▼
FilePreviewInline → FileContentRenderer
    ├── source code (<pre>)
    ├── markdown (ReactMarkdown)
    ├── HTML (iframe)
    ├── PDF (iframe)
    └── images (<img>) → click → FullscreenPreview
```

---

## Design System

The UI follows the **SIGNAL** design language (see `design/DESIGN_LANGUAGE.md`). Key architectural choices:

- **CSS Modules** — Per-component styles (`*.module.css`), no global class collisions
- **Semantic tokens** — All colors reference `--canvas`, `--surface`, `--accent`, etc., never raw values
- **Theme switching** — `data-theme="light|dark"` attribute on `<html>` swaps all token values
- **Terminal tokens** — Code blocks and terminal output use a separate set of theme-aware tokens (`--terminal-bg`, `--terminal-text`, etc.) that adapt per theme
- **Share Tech Mono** — Structural UI elements (headers, agent names, status labels) use monospace to reinforce the COMPUTRON identity

---

## Known Technical Debt

1. **Global button CSS bleeds** — The `button` rule in `global.css` applies opinionated styles to all buttons. Every utility button must override. Should scope to a `.btn` class.

2. **JSONL event schema is ad-hoc** — The SSE stream lacks a uniform envelope. Fields live at different nesting levels, forcing ~350 lines of conditional routing in `useStreamingChat.js`. Should normalize to a consistent envelope with `type`, `agent_id`, `depth` at the top level.

3. **Terminal lines are unbounded** — Terminal output is append-only with no max-line limit. Long-running agents could accumulate large arrays.

