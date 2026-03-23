# UI Architecture

## Conceptual Framework

The UI has two fundamental display paradigms:

- **Chat View** — A multi-turn conversation between the user and the root agent. Messages accumulate as a scrollable thread. Used for direct interaction.
- **Activity View** — A real-time log of a single agent's work: thinking, content, tool calls, file outputs. Used for observing sub-agents (or the root agent when drilled in from the network).

Both views consume the same SSE event stream but route data through different state systems. The long-term goal is to share rendering components between them and eliminate duplication.

---

## View Modes

The UI has three layout modes, determined by agent state:

```
┌──────────────────────────────────────────────────────┐
│                    View Mode Selection                │
│                                                      │
│  selectedAgentId?  ──yes──▶  MODE 1: Activity View   │
│        │                                             │
│        no                                            │
│        │                                             │
│  hasSubAgents?  ──yes──▶  MODE 2: Network + Chat     │
│        │                                             │
│        no                                            │
│        │                                             │
│        ▼                                             │
│  MODE 3: Simple Chat                                 │
└──────────────────────────────────────────────────────┘
```

**Mode 1 — Agent Activity View** (`selectedAgentId !== null`)
```
┌──────┬──────────────────────────────────────────────────┐
│      │ ← Agents  COMPUTRON 9000 › BROWSER AGENT         │
│ Side │ ● BROWSER AGENT  32s  iter 5  ◐ 8%              │
│ bar  │──────────────────────────────────────────────────│
│      │  Activity (40%)     │  Previews (60%)            │
│      │                     │                            │
│      │  [Instruction]      │  ┌─────────────────────┐  │
│      │  ▸ Show thoughts    │  │ Browser              │  │
│      │  Content text...    │  │ https://example.com  │  │
│      │  🔧 open_url        │  │ ┌─────────────────┐ │  │
│      │  ▸ Show thoughts    │  │ │  screenshot     │ │  │
│      │  Content text...    │  │ └─────────────────┘ │  │
│      │                     │  └─────────────────────┘  │
│      │──────────────────────────────────────────────────│
│      │  Nudge  [Send a nudge to root agent...]          │
└──────┴──────────────────────────────────────────────────┘
```

**Mode 2 — Network + Chat** (`hasSubAgents && !selectedAgent`)
```
┌──────┬────────────────────────────┬─────────────────────┐
│      │     Agent Network          │  Chat               │
│ Side │                            │                     │
│ bar  │   ┌──────────────┐         │  [user] yo          │
│      │   │ COMPUTRON 9000│         │                     │
│      │   └──────┬───────┘         │  COMPUTRON ◐ 4%     │
│      │          │                 │  ▸ Show thoughts     │
│      │   ┌──────┴───────┐         │  Hey Larry! 👋       │
│      │   │BROWSER AGENT │         │                     │
│      │   └──────────────┘         │  [user] search...   │
│      │                            │                     │
│      │   (60%)                    │  (40%)              │
│      │                            │                     │
│      │                            │  [Type message...]  │
└──────┴────────────────────────────┴─────────────────────┘
```

**Mode 3 — Simple Chat** (default, no sub-agents)
```
┌──────┬───────────────────────────┬──────────────────────┐
│      │  Previews (60%)           │  Chat (40%)          │
│ Side │  ┌─────────────────────┐  │                      │
│ bar  │  │ Generating Image    │  │  [user] draw a cat   │
│      │  │ ████░░░░  33%       │  │                      │
│      │  └─────────────────────┘  │  COMPUTRON ◐ 3%      │
│      │  ┌─────────────────────┐  │  ▸ Show thoughts     │
│      │  │ 🟢 Terminal          │  │  Here's your cat!    │
│      │  │ $ python draw.py    │  │                      │
│      │  │ Done.               │  │                      │
│      │  └─────────────────────┘  │  [Type message...]   │
└──────┴───────────────────────────┴──────────────────────┘
```

---

## State Architecture

Two independent state systems manage different concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    SSE Event Stream                          │
│                   (JSONL from /api/chat)                     │
└─────────────┬───────────────────────────────────┬───────────┘
              │                                   │
              ▼                                   ▼
┌─────────────────────────┐       ┌───────────────────────────┐
│   useStreamingChat      │       │   useAgentState           │
│   (React hooks)         │       │   (Context + Reducer)     │
│                         │       │                           │
│  messages[]             │       │  agents: {                │
│    - user messages      │       │    [id]: {                │
│    - root agent replies │       │      activityLog[],       │
│    - tool call data     │       │      browserSnapshot,     │
│    - context usage      │       │      terminalLines,       │
│    - streaming state    │       │      contextUsage,        │
│                         │       │      status, iteration    │
│  Consumers:             │       │    }                      │
│    ChatMessages         │       │  }                        │
│    Message              │       │  selectedAgentId          │
│                         │       │                           │
│                         │       │  Consumers:               │
│                         │       │    AgentNetwork            │
│                         │       │    AgentCard               │
│                         │       │    AgentActivityView       │
└─────────────────────────┘       └───────────────────────────┘
```

### Event Routing

Depth determines where streaming tokens go:

```
SSE delta event arrives
        │
        ├── depth == 0 (root agent)
        │   ├── Buffer in pendingContent / pendingThinking
        │   ├── Flush per requestAnimationFrame
        │   └── setMessages() → Chat View renders it
        │
        └── depth > 0 (sub-agent)
            ├── Buffer in agentPending[agentId]
            ├── Flush per requestAnimationFrame
            └── agentDispatch(APPEND_STREAM_CHUNK) → Activity View renders it
```

Non-streaming events (tool calls, screenshots, lifecycle) route through `_handleStreamEvent` callbacks that update **both** state systems for backward compatibility:

```
onBrowserSnapshot(snapshot)
    ├── setBrowserSnapshot(snapshot)          // Global (Mode 3 preview panel)
    └── agentDispatch(UPDATE_BROWSER_SNAPSHOT) // Per-agent (Mode 1 preview)
```

---

## Component Tree

```
AgentStateProvider
└── DesktopAppInner
    ├── Header ─── [desktop button, theme, new conversation]
    │
    ├── Sidebar ─── [agents, settings, memory, conversations, tools]
    │
    ├── FlyoutPanel? ─── [ModelSettingsPanel | MemoryPanel | ConversationsPanel | CustomToolsPanel]
    │
    ├── mainContent (one of three modes)
    │   │
    │   ├── AgentActivityView ──── Mode 1
    │   │   ├── ActivityEntry[] ── [CollapsibleThinking | ContentBlock | ToolBlock | FileOutput]
    │   │   ├── BrowserPreview
    │   │   ├── TerminalPanel
    │   │   ├── DesktopPreview
    │   │   └── GenerationPreview
    │   │
    │   ├── networkWithChat ────── Mode 2
    │   │   ├── AgentNetwork
    │   │   │   └── AgentCard[]
    │   │   └── ChatPanel
    │   │       ├── ChatMessages
    │   │       │   └── Message[] ── [MarkdownContent, ToolCallsSummary, ContextUsageBadge, FileOutput]
    │   │       └── ChatInput
    │   │
    │   └── simpleChat ────────── Mode 3
    │       ├── previewColumn?
    │       │   ├── GenerationPreview
    │       │   ├── BrowserPreview
    │       │   ├── DesktopPreview
    │       │   └── TerminalPanel
    │       └── ChatPanel (same as Mode 2)
    │
    ├── DesktopPreview (overlay, Modes 1-2 only)
    ├── FilePreview (overlay, all modes)
    └── nudgeToast
```

---

## Shared vs. Duplicated Components

Components used in **both** Chat View and Activity View:

| Component | Chat View (Message.jsx) | Activity View (AgentActivityView.jsx) | Shared? |
|---|---|---|---|
| **MarkdownContent** | Content rendering | Content + instruction rendering | Yes |
| **ContextUsageBadge** | Message header | Agent header | Yes |
| **FileOutput** | In message.data[] | In activityLog | Yes |
| **CollapsibleThinking** | Thinking toggle in messages | Thinking toggle in activity entries | Yes (compact prop for activity view) |
| **BrowserPreview** | Mode 3 preview column | Mode 1 right pane | Yes |
| **TerminalPanel** | Mode 3 preview column | Mode 1 right pane | Yes |
| **DesktopPreview** | Mode 3 preview column | Mode 1 overlay | Yes |
| **GenerationPreview** | Mode 3 preview column | Mode 1 right pane | Yes |

Shared hooks:

| Hook | Used by | Purpose |
|---|---|---|
| **useAutoScroll** | ChatMessages, AgentActivityView | Scroll to bottom on updates unless user scrolled up |
| **useAgentState** | AgentNetwork, AgentActivityView, AgentCard | Read agent tree state |
| **useAgentDispatch** | DesktopApp, AgentNetwork, AgentActivityView | Dispatch agent state actions |

Components with **different implementations** for each view (by design):

| Concept | Chat View | Activity View | Notes |
|---|---|---|---|
| **Tool call display** | ToolCallsSummary (compact badge) | ActivityEntry tool_call (inline with icon) | Different density needs |

---

## Preview Panel Lifecycle

Preview panels appear in different contexts depending on view mode:

```
                    Mode 3              Mode 1              Mode 2
                  (simple chat)      (activity view)     (network + chat)
                  ─────────────      ───────────────     ────────────────
BrowserPreview    Inline panel       Right pane          Not shown
TerminalPanel     Inline panel       Right pane          Not shown
DesktopPreview    Inline panel       Overlay lightbox    Overlay lightbox
GenerationPreview Inline panel       Right pane          Not shown
FilePreview       Overlay            Overlay             Overlay
```

---

## Known Technical Debt

1. **Dual state updates** — Every event updates both global state (for Mode 3) and per-agent state (for Modes 1-2). Should consolidate to per-agent only and derive Mode 3 state from `agents[rootId]`.

2. **JSONL event schema is ad-hoc** — The stream uses JSONL-over-POST (which is fine as a transport), but the event format lacks a uniform envelope. Fields live at different nesting levels (`data.delta`, `data.event.type`, `data.final`, `data.depth`, `data.agent_id`), forcing the frontend into ~350 lines of conditional routing in `useStreamingChat.js`. Should normalize to a consistent envelope where every line has `type`, `agent_id`, `depth` at the top level, turning the routing into a simple `switch(data.type)`. This touches both backend emission (`_execution.py`, `message_handler.py`) and frontend consumption (`useStreamingChat.js`). Prioritize after dual-state consolidation since both touch the same pipeline.

### Resolved

- ~~Missing callbacks in AgentActivityView~~ — `FileOutput.onPreview` now wired through `onPreview` prop.
- ~~showSubAgents prop unused~~ — Removed prop and dead filtering logic.
- ~~Thinking toggle duplicated~~ — Extracted shared `CollapsibleThinking` component with `compact` prop for activity view sizing.
- ~~Auto-scroll duplicated~~ — Extracted `useAutoScroll` hook used by both `ChatMessages` and `AgentActivityView`.
