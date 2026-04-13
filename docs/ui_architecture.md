# UI Architecture

## Conceptual Framework

The UI has two fundamental display paradigms:

- **Chat View** — A multi-turn conversation between the user and the root agent. Messages accumulate as a scrollable thread. Always mounted (hidden when other views are active to preserve scroll and input state).
- **Activity View** — A real-time log of a single agent's work: thinking, content, tool calls, file outputs. Shown when drilling into an agent from the network graph.

Both views share a **tabbed preview panel** on the right side for browser screenshots, terminal output, file previews, desktop VNC, and media generation.

---

## Layout

The UI uses a split layout: the main view on the left, an optional tabbed preview panel on the right, with a draggable divider between them.

```
┌──────┬─────────────────────────────┬───┬──────────────────┐
│      │                             │   │  [tabs]          │
│ Side │  Main View                  │ ┃ │  Browser         │
│ bar  │  (Chat / Activity /         │ ┃ │  file.py    ×    │
│      │   Network / Goals /         │ ┃ │  Terminal        │
│      │   Settings)                 │ ┃ │─────────────────│
│      │                             │ ┃ │  Preview content │
│      │                             │ ┃ │                  │
│      │                             │   │                  │
└──────┴─────────────────────────────┴───┴──────────────────┘
                                      ↑
                                   drag handle
```

The left side shows one of:
- **Chat** (default) — always mounted, hidden via CSS when others are active
- **Agent Activity** — when a sub-agent is selected from the network graph
- **Network Graph** — full-width agent tree view
- **Goals** — full-width goals management
- **Settings** — full-width settings page

The preview panel is visible alongside Chat and Agent Activity, but hidden during Network Graph, Goals, and Settings (full-width views).

---

## State Architecture

### Agent Reducer (single source of truth for preview data)

All preview data lives in the agent reducer (`useAgentState`). Each agent node holds its own preview state:

```
agents: {
  [agentId]: {
    activityLog[]        // thinking, content, tool calls, file outputs
    browserSnapshot      // latest screenshot + URL + title
    terminalLines[]      // bash command history (append-only)
    desktopActive        // VNC session flag
    generationPreview    // image/video/audio generation state
    openFiles[]          // files opened in preview tabs
    status               // running | success | error | stopped
    iteration            // current loop iteration
    contextUsage         // context window fill percentage
    ...
  }
}
```

### Preview State Hook (`usePreviewState`)

Extracts all preview panel logic from DesktopApp into a single hook:

```
usePreviewState(agentState, agentDispatch)
  → tabs[]           // computed from previewAgent's data
  → activeTab        // which tab is selected
  → splitPosition    // drag handle percentage (20-80)
  → fullscreenItem   // file in fullscreen mode (or null)
  → openFile(item)   // dispatches OPEN_FILE to reducer
  → closeTab(id)     // dispatches appropriate close action
  → reset()          // clears UI-only state for new conversations
  → browserSnapshot, terminalLines, ...  // derived from active agent
```

The hook determines which agent's previews to show:
- When a sub-agent is selected → show that agent's data
- Otherwise → show the root agent's data

### Chat State (`useStreamingChat`)

Manages the conversation separately from agent state:

```
useStreamingChat(callbacks)
  → messages[]       // user + assistant messages
  → isStreaming      // whether a response is in flight
  → sendMessage()
  → stopGeneration()
  → loadConversation()
  → newConversation()
```

---

## Event Flow

### Backend → UI Pipeline

```
Backend SSE stream (/api/chat)
    │
    ▼
useStreamingChat
    │
    ├── depth == 0 (root agent tokens)
    │   └── Buffer → requestAnimationFrame → setMessages()
    │       → Chat View renders
    │
    └── depth > 0 (sub-agent tokens)
        └── Buffer → requestAnimationFrame → agentDispatch(APPEND_STREAM_CHUNK)
            → Activity View renders
```

### Preview Events

Preview events (screenshots, terminal output, desktop, generation, files) are dispatched to the agent reducer via stable `useRef` callbacks. This avoids stale closure problems since the callbacks are created once and use dispatch/setState updaters.

```
onBrowserSnapshot(snapshot)
    → agentDispatch({ type: 'UPDATE_BROWSER_SNAPSHOT', agentId, snapshot })

onTerminalOutput(event)
    → agentDispatch({ type: 'UPDATE_TERMINAL', agentId, event })
    (terminal lines are append-only via mergeTerminalEvent)

onDesktopActive(agentId)
    → agentDispatch({ type: 'UPDATE_DESKTOP_ACTIVE', agentId })

onGenerationPreview(event)
    → agentDispatch({ type: 'UPDATE_GENERATION_PREVIEW', agentId, preview })
```

The preview hook reads from the reducer and computes tabs automatically — no dual state updates needed.

### Agent Lifecycle Events

```
onAgentEvent({ type: 'agent_started', ... })
    → agentDispatch({ type: 'AGENT_STARTED', ... })
    (new root agents carry over browser/terminal/desktop/generation from previous root)

onAgentEvent({ type: 'agent_completed', ... })
    → agentDispatch({ type: 'AGENT_COMPLETED', ... })
```

### File Preview Events

Files from agent output appear in the chat/activity stream via `FileOutput`. Clicking "Preview" dispatches to the reducer:

```
User clicks Preview on a file
    → preview.openFile(item)
    → agentDispatch({ type: 'OPEN_FILE', agentId, item })
    → usePreviewState recomputes tabs, sets active tab
```

Same-filename files replace the existing tab. Different filenames open new tabs. Non-previewable files (binaries) download directly instead.

---

## Component Tree

```
AgentStateProvider
└── DesktopAppInner
    ├── Header
    ├── Sidebar
    ├── FlyoutPanel?
    │
    ├── mainContent
    │   ├── SettingsPage                    (full-width)
    │   ├── GoalsView                       (full-width)
    │   ├── AgentNetwork                    (full-width)
    │   ├── AgentActivityView               (left column, shares preview panel)
    │   │   └── AgentOutput
    │   │       └── FileOutput              (click → opens in preview panel)
    │   ├── ChatPanel                       (left column, always mounted)
    │   │   ├── ChatMessages → Message → AgentOutput → FileOutput
    │   │   └── ChatInput
    │   │
    │   ├── SplitHandle                     (drag divider)
    │   └── PreviewPanel                    (right column, shared)
    │       ├── [tab bar]
    │       ├── BrowserPreview (hideShell)
    │       ├── FilePreviewInline
    │       │   └── FileContentRenderer
    │       ├── TerminalPanel (hideShell)
    │       ├── DesktopPreview (hideShell)
    │       └── GenerationPreview (hideShell)
    │
    ├── DesktopPreview (overlay, user-initiated)
    ├── FullscreenPreview (viewport takeover for files)
    └── SetupWizard (shown if setup incomplete)
```

### Preview Components

Preview components support two rendering modes via the `hideShell` prop:

- **With shell** (`hideShell=false`): Wrapped in `PreviewShell` with title bar, close button, expand button. Used in legacy contexts.
- **Without shell** (`hideShell=true`): Bare content only. Used inside the tabbed `PreviewPanel` where the tab bar provides chrome.

### File Preview Stack

```
FileOutput (in chat/activity stream)
    │ click "Preview"
    ▼
usePreviewState.openFile(item)
    │ dispatches OPEN_FILE
    ▼
PreviewPanel tab appears
    │
    ▼
FilePreviewInline
    ├── toolbar (filename, source/preview toggle, download, fullscreen)
    └── FileContentRenderer
        ├── source code (<pre>)
        ├── markdown (ReactMarkdown)
        ├── HTML (iframe)
        ├── PDF (iframe, browser built-in viewer)
        └── images (<img>)
            │ click "Fullscreen"
            ▼
        FullscreenPreview (same renderer, viewport-filling)
```

File type detection uses shared utilities in `utils/fileTypes.js`:
- `canPreviewFile()` — determines if a file opens in a tab or downloads
- `hasPreviewToggle()` — whether source/preview toggle is shown (markdown, HTML)
- `isImageFile()`, `isPdfFile()` — type checks

---

## Known Technical Debt

1. **Global button CSS bleeds into utility buttons** — The global `button` rule in `global.css` applies `background`, `padding`, `box-shadow`, `border-radius` to all buttons. Every utility button (tabs, icon buttons, toggles) must override these. Should scope the opinionated styles to a `.btn` class. See `docs/plans/global-button-refactor.md`.

2. **JSONL event schema is ad-hoc** — The stream uses JSONL-over-POST but lacks a uniform envelope. Fields live at different nesting levels, forcing ~350 lines of conditional routing in `useStreamingChat.js`. Should normalize to a consistent envelope.

3. **Terminal lines are unbounded** — Terminal output is append-only with no max-line limit. Long-running agents could accumulate large arrays.

### Resolved

- ~~Dual state updates~~ — Preview data now lives only in the agent reducer. The preview hook derives everything from the active agent.
- ~~Preview panels duplicated between views~~ — Shared tabbed preview panel used by both chat and activity views.
- ~~openFiles in wrong state~~ — Moved from local component state to the agent reducer.
- ~~Missing file preview callbacks~~ — `FileOutput.onPreview` wired through all views.
- ~~Thinking toggle duplicated~~ — Shared `CollapsibleThinking` component.
- ~~Auto-scroll duplicated~~ — Shared `useAutoScroll` hook.
