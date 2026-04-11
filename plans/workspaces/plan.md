# Workspaces Feature — Design Plan

## Context

Workspaces give each project/context full disk isolation: its own filesystem, memory, conversations, and goals. The agent always sees `/home/computron` regardless of which workspace is active — isolation is transparent. There's always a "Default" workspace; users can create more.

Workspaces are **tabbed** — multiple can be open and running simultaneously. An agent in one workspace can be mid-turn while the user works in another tab.

This design sits on top of the `ux-improvements` refactor (single root agent + skills + agent profiles). Skills and profiles are **global**. Workspaces scope *where* the agent operates (data isolation); skills/profiles scope *how* (capabilities and tuning).

---

## Design Decisions

| Decision | Choice |
|----------|--------|
| Workspace selector | Full-screen picker (via [+] tab) |
| Tab style | Compact header tabs (integrated into header row) |
| App launch | Remember last open tabs; first-ever launch → default |
| Activity indicator | Color change on tab when agent is running |
| Creation dialog | Full: name, description, clone, upload |
| Agent home path | Keep `/home/computron` (transparent isolation) |
| Skills | Global (shared across all workspaces) |
| Profiles | Global (becoming "agent profiles" per ux-improvements plan) |
| Tab close | Right-click context menu (close/rename/manage) |
| Closing a tab | Does NOT delete the workspace, just closes it |

---

## UI Mockups

### 1. Compact Header Tabs

```
┌───────────────────────────────────────────────────────────────┐
│ CT9K  Default | Research | Client  [+]            theme      │
├────┬──────────────────────────────────────────────────────────┤
│ AG │                                                          │
│ GL │                                                          │
│ ST │           Chat (scoped to active tab's workspace)        │
│ ME │                                                          │
│ CV │                                                          │
│ TL │                                                          │
└────┴──────────────────────────────────────────────────────────┘
```

- Active tab is visually distinct (bold / underline / background)
- Inactive tab with running agent gets a color indicator (e.g., green text)
- Sidebar panels (Memory, Conversations, etc.) are scoped to the active tab's workspace
- Right-click a tab → context menu: Rename, Manage, Close

### 2. Full-Screen Workspace Picker (click [+])

```
┌───────────────────────────────────────────────────────────────┐
│ CT9K  Default | Research |  [+]                   theme      │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│                    Select a Workspace                         │
│                                                               │
│   ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│   │  Default        │  │  Research      │  │  Client Demo   │ │
│   │  Workspace      │  │  Project       │  │                │ │
│   │                 │  │                │  │  1 convo       │ │
│   │  12 convos     │  │  7 convos      │  │  15 MB         │ │
│   │  247 MB        │  │  82 MB         │  │                │ │
│   │       [open]   │  │       [open]   │  │       [open]   │ │
│   └────────────────┘  └────────────────┘  └────────────────┘ │
│                                                               │
│   ┌────────────────┐                                          │
│   │                │                                          │
│   │  + Create New  │                                          │
│   │   Workspace    │                                          │
│   │                │                                          │
│   └────────────────┘                                          │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

- Cards for existing workspaces show name, description snippet, stats
- Already-open workspaces are visually marked (e.g., "open" badge) — clicking focuses that tab
- "+ Create New" card opens the creation dialog

### 3. Create Workspace Dialog

```
┌──────────────── Create Workspace ─────────────────┐
│                                                    │
│  Name:                                             │
│  ┌──────────────────────────────────────────┐      │
│  │                                          │      │
│  └──────────────────────────────────────────┘      │
│                                                    │
│  Description (optional):                           │
│  ┌──────────────────────────────────────────┐      │
│  │                                          │      │
│  └──────────────────────────────────────────┘      │
│                                                    │
│  Starter files:                                    │
│  ( ) Empty workspace                               │
│  ( ) Clone files from: [Default Workspace  v]      │
│  ( ) Upload files  [Choose Files]                  │
│                                                    │
│                    [Cancel]   [Create]              │
└────────────────────────────────────────────────────┘
```

- "Clone from" copies filesystem contents only (not conversations/memory)
- "Upload files" opens a file picker
- Created workspace opens immediately as a new tab

### 4. Tab Context Menu (right-click)

```
             ┌──────────────────┐
             │ Rename           │
             │ Workspace Info   │
             │ ──────────────── │
             │ Close Tab        │
             │ Delete Workspace │
             └──────────────────┘
```

- "Close Tab" removes from tab bar, workspace persists
- "Delete Workspace" shows confirmation (disabled for default)
- "Workspace Info" shows stats (disk usage, conversation count, etc.)

### 5. Color Indicator for Running Agent

```
┌───────────────────────────────────────────────────────────────┐
│ CT9K  Default | Research | Client  [+]            theme      │
│                  ^^^^^^^^                                     │
│                  (green = agent running in this workspace)    │
└───────────────────────────────────────────────────────────────┘
```

---

## Backend Architecture

### Directory Layout

```
~/.computron_9000/
├── workspaces.json              # registry + tab state
├── workspaces/
│   ├── default/
│   │   ├── home/                # agent sees as /home/computron
│   │   │   └── uploads/
│   │   ├── conversations/
│   │   │   └── {conv_id}/
│   │   │       ├── history.json
│   │   │       ├── metadata.json
│   │   │       └── events.json
│   │   ├── memory.json
│   │   └── goals/
│   │
│   ├── research-project/
│   │   ├── home/
│   │   ├── conversations/
│   │   ├── memory.json
│   │   └── goals/
│   │
│   └── client-demo/
│       └── (same structure)
```

### workspaces.json

```json
{
  "workspaces": [
    {
      "id": "default",
      "name": "Default Workspace",
      "description": "",
      "created_at": "2026-04-01T00:00:00Z"
    },
    {
      "id": "research-project",
      "name": "Research Project",
      "description": "Browser-based research tasks",
      "created_at": "2026-04-05T12:00:00Z"
    }
  ],
  "open_tabs": ["default", "research-project"],
  "active_tab": "research-project"
}
```

### WorkspaceContext

Central object that resolves all paths for a workspace. Replaces scattered path references throughout the codebase.

```
WorkspaceContext(workspace_id="research-project")
  .home_dir        → ~/.computron_9000/workspaces/research-project/home/
  .conversations   → ~/.computron_9000/workspaces/research-project/conversations/
  .memory_file     → ~/.computron_9000/workspaces/research-project/memory.json
  .goals_dir       → ~/.computron_9000/workspaces/research-project/goals/
```

Every system that reads/writes data (conversations, memory, fs tools, goals) receives a `WorkspaceContext` instead of building paths from global config.

### Multi-Tab Server State

Since multiple workspaces can be active simultaneously:

- Server maintains a dict of active workspace contexts: `{workspace_id: WorkspaceContext}`
- Each `/api/chat` request includes `workspace_id` to route to the correct context
- Conversation state (`_conversations` dict in `message_handler.py`) is keyed by `(workspace_id, conversation_id)` instead of just `conversation_id`
- Agent turns in different workspaces are fully independent — separate message histories, separate tool contexts

### API Endpoints

```
GET    /api/workspaces                  # list all workspaces
POST   /api/workspaces                  # create {name, description, clone_from?}
GET    /api/workspaces/:id              # workspace details + stats
PUT    /api/workspaces/:id              # rename / update description
DELETE /api/workspaces/:id              # delete (not default)

GET    /api/workspaces/tabs             # get open tabs + active tab
PUT    /api/workspaces/tabs             # update open tabs + active tab

# Existing endpoints gain workspace_id parameter:
GET    /api/conversations/sessions?workspace=:id
POST   /api/chat                        # body includes workspace_id
GET    /api/memory?workspace=:id
```

### Migration (Existing Data → Default Workspace)

On first run with workspaces enabled:
1. Create `workspaces/default/` directory
2. Move `{home_dir}/conversations/` → `workspaces/default/conversations/`
3. Move `{home_dir}/memory.json` → `workspaces/default/memory.json`
4. Move `{home_dir}/goals/` → `workspaces/default/goals/`
5. Symlink or remap `virtual_computer.home_dir` contents → `workspaces/default/home/`
6. Create `workspaces.json` with default entry and `open_tabs: ["default"]`

---

## Implementation Phases

### Phase 1: Backend — WorkspaceContext + Storage
- `WorkspaceContext` model and workspace registry (CRUD)
- Refactor `conversations/_store.py` to accept workspace context
- Refactor `tools/memory/` to accept workspace context
- Refactor `tools/fs/` path resolution to use workspace home dir
- Migration logic for existing data
- API endpoints for workspace CRUD

### Phase 2: Backend — Multi-Workspace Concurrency
- Key conversation state by `(workspace_id, conversation_id)`
- Route `/api/chat` requests to correct workspace context
- Ensure agent tool calls (fs, memory, bash) use the correct workspace's paths
- Tab state persistence (open tabs, active tab)

### Phase 3: Frontend — Tabs + Picker
- Compact header tab bar component
- Full-screen workspace picker/creator
- Create workspace dialog (name, description, clone, upload)
- Tab context menu (right-click: rename, info, close, delete)
- Wire workspace_id into all API calls
- Scope sidebar panels (Conversations, Memory) to active workspace tab

### Phase 4: Frontend — Polish
- Color indicator for tabs with running agents
- Remember open tabs on app reload
- Workspace stats (disk usage, conversation count) on picker cards
- First-run experience (auto-open default workspace)

---

## Files to Modify (Key)

**New files:**
- `workspaces/_models.py` — `Workspace`, `WorkspaceContext`, `WorkspaceRegistry`
- `workspaces/_store.py` — CRUD, migration, tab state persistence
- `server/ui/src/components/WorkspaceTabs.jsx` — tab bar component
- `server/ui/src/components/WorkspacePicker.jsx` — full-screen picker
- `server/ui/src/components/CreateWorkspaceDialog.jsx` — creation dialog
- `server/ui/src/hooks/useWorkspaces.js` — workspace state management

**Modified files:**
- `config/__init__.py` — workspace-aware path resolution
- `conversations/_store.py` — accept `WorkspaceContext` for all operations
- `tools/memory/memory.py` — workspace-scoped memory file path
- `tools/fs/` — resolve paths against workspace home dir
- `tools/virtual_computer/receive_file.py` — upload to workspace home
- `server/message_handler.py` — key conversations by workspace, route requests
- `server/aiohttp_app.py` — workspace API endpoints, workspace_id in existing routes
- `server/ui/src/components/Header.jsx` — embed tab bar
- `server/ui/src/hooks/useStreamingChat.js` — include workspace_id in requests
- `server/ui/src/App.jsx` / `DesktopApp.jsx` — workspace-scoped app state

---

## Verification

- Existing tests pass (workspace defaults to "default", no breaking changes)
- Create workspace → files appear in `~/.computron_9000/workspaces/{id}/`
- Agent file operations land in correct workspace's `home/`
- Memory in workspace A is invisible from workspace B
- Conversations list is scoped per workspace
- Two workspace tabs open → run agent in tab A → switch to tab B → agent still running in A (color indicator)
- Close tab → reopen from picker → workspace data intact
- App restart → same tabs reopen
- Delete workspace → files removed, tab closes, can't delete default
