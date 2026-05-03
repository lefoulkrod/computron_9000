# Integrations — Follow-Up Work

> Consolidated plan for what's deferred from `integrations-v1`. The shipped surface is documented in [`docs/integrations.md`](../docs/integrations.md); this file is for what's *next*.

The v1 PR shipped:

- Supervisor + broker UID split, AES-256-GCM vault crypto.
- Email broker (IMAP + SMTP) and CalDAV reads, both with reconnect-on-idle.
- App-password auth (iCloud + Gmail) via inline catalog entries.
- HTTP API: `GET / POST / PATCH / DELETE /api/integrations[/:id]`.
- React UI: master-detail Integrations tab with Add wizard, label edit, write_allowed toggle, delete.
- Container entrypoint with `gosu broker` + tmpfs sockets.
- E2E tests for the empty/unavailable/Add-modal flows.

What's *not* in v1 falls into three buckets, in roughly the order I'd ship them.

---

## Bucket 1 — Catalog & auth-plugin decomposition

**Why:** Adding new email/calendar providers (Fastmail, Outlook.com, custom IMAP) currently means editing `_catalog.py`. The plan was always for catalog entries to live as JSON files and auth plugins as standalone modules. Moving the existing iCloud + Gmail entries to that shape is a small mechanical refactor that unlocks one-file-PR additions afterward.

**Scope:**

- **JSON catalog loader.** Move `_ICLOUD` and `_GMAIL` from `_catalog.py` into `config/integrations_catalog/icloud.json` and `gmail.json`. `_catalog.py` becomes a loader that reads the dir, validates each file with the existing `CatalogEntry` Pydantic model, and fails loud if anything's malformed. (Plan: original `07-catalog.md`.)
- **Catalog endpoint.** `GET /api/integrations/catalog` (list) and `GET /api/integrations/catalog/:slug` (one merged entry). Today the UI hardcodes `PROVIDERS` in `AddIntegrationModal.jsx` — switch it to fetch from the endpoint.
- **`auth_plugins/` package.** Extract `app_password` (iCloud + Gmail) and `api_key` (used later by GitHub) into standalone modules with `FIELDS` + `ENV_INJECTION`. Catalog `auth_plugin` field references them by name. (Plan: `04-auth-plugins.md`.)
- **Field overrides.** Per-provider tweaks live in the catalog entry's `field_overrides` block (deep-link URL, hint text, regex). Today these are baked into the React provider list.

**Out of scope for this bucket:** new providers. The point is to make adding them cheap, not to add a bunch at once.

**Tests:**

- Pydantic round-trip on each JSON file at startup; fail-loud test that a malformed file kills the supervisor.
- Golden snapshot of the merged `/catalog/icloud` response so accidental schema drift fails CI.
- e2e: Add modal still works (provider list now comes from the API).

---

## Bucket 2 — MCP broker + GitHub integration

**Why:** This is the second half of the v1 slate. We have email/calendar; MCP unlocks GitHub, Linear, Notion, Home Assistant, and any future stdio MCP server with one catalog entry per provider.

**Scope:** (largely what original `03-broker-mcp.md` described)

- **`integrations/brokers/mcp_broker/` package.** Stdio host that:
  1. Spawns the MCP subprocess (`uvx <pkg>`, `npx <pkg>`, etc.) with creds in env.
  2. Sends `initialize`, then `tools/list` to verify (empty list = treat as auth fail, exit 77).
  3. Builds a `tool_name → readOnlyHint` map.
  4. Prints `READY\n`, opens its UDS, relays JSON-RPC frames between UDS and the subprocess's stdin/stdout.
- **Write enforcement at `tools/call`.** The MCP broker is the security boundary, mirroring how email_broker gates write verbs at dispatch. With `WRITE_ALLOWED=false`, refuse `tools/call` for any tool whose `readOnlyHint` is missing or false. Locally rejected — subprocess never sees the call.
- **`notifications/tools/list_changed` handling.** When the upstream MCP server signals tool changes, re-run `tools/list` and rebuild the read-only map before forwarding.
- **JSON-RPC ID rewriting in the relay.** Prevent ID collisions between UDS clients and the subprocess. Reverse on the way back.
- **GitHub catalog entry.** `config/integrations_catalog/github.json` — `auth_plugin: api_key`, `kinds: ["mcp"]`, broker command runs `uvx github-mcp` with the PAT injected.
- **`api_key` auth plugin.** Single-token field, deep-link to GitHub PAT page (overrideable per-catalog-entry for Linear / Notion / etc.).
- **`stub_mcp_server` test fixture.** Runs as a real subprocess, implements `initialize` + `tools/list` + one read-only tool + one write tool. Configurable via env (`STUB_MCP_AUTH_FAIL=1` for the empty-tools-list path, `STUB_MCP_HANG=N` for handshake-timeout tests).
- **`server/mcp_bridge.py`.** Translates the broker's MCP tools into agent-visible tools. Re-registers the agent's tool list when integrations come/go or when `tools/list_changed` fires. Hides write-tagged tools when `write_allowed=false`.

**Cross-cutting:**

- `_VERB_TYPE` in `email_broker/_verbs.py` and the mirror in `broker_client/_verb_types.py` don't apply to MCP — the broker's tool-level read-only map is per-instance, not per-verb. The drift-check test should explicitly skip MCP brokers.
- `tools_exposed: ["__dynamic__"]` in the catalog signals "ask the broker post-spawn for the tool list" (UI display + agent registry).

**Tests:** described in original `03-broker-mcp.md` — happy path, auth-fail (empty tools), initialize timeout, shutdown grace, ID rewriting, write enforcement, list-changed refresh.

---

## Bucket 3 — Operational & UX polish

**Why:** Each item below is independently useful but not blocking either of the buckets above. Order is rough priority.

- **Connection pool + resolve cache** in `broker_client._call`. Today the comment at the top says "walking-skeleton shape: no resolve-cache, no connection pool, one UDS connection per call()". Under heavy agent use this hammers the supervisor's RPC. ~500ms TTL on resolve, per-broker connection pool with idle eviction.
- **`/api/integrations/events` (SSE).** State-change push to the UI so the integrations list updates live when a broker flips to `auth_failed` mid-session. Today the UI only refreshes on PATCH/DELETE round-trips.
- **REST verb split.** Today `PATCH /api/integrations/:id` covers label and write_allowed. The original plan also called for `/verify`, `/reconnect`, `/enable`, `/disable` as distinct endpoints. Add when the UI grows the affordances.
- **Calendar writes** (`create_event`, `update_event`, `delete_event` on `_caldav_client.py`). The verb names exist in `_VERB_TYPE` but the handlers aren't wired; today they error as `BAD_REQUEST: "verb not implemented"`. Either remove the type-table entries until shipped or wire the handlers + UI affordance.
- **IMAP `flag_message`.** Set/clear `\Seen`, `\Flagged`. Single message and bulk variant matching `move_messages` shape.
- **Downloads-dir GC sweeper.** Email-attachment side-channel writes to `/run/cvault/attachments/`; broker holds ownership but there's no scheduled cleanup. Add a 60s sweep that prunes anything older than N minutes.
- **Search v2.** Today `search_messages` exposes IMAP `SEARCH TEXT` only. Real Gmail uses `X-GM-RAW`; iCloud's IMAP supports more criteria. The agent-facing tool currently just passes a string; richer search would benefit from structured criteria (from/to/subject/before/after).
- **`broker_client` error class hierarchy.** Today every wire error becomes `IntegrationError`; callers that want to differentiate AUTH from NETWORK have to string-match the message. Split into subclasses for AUTH / NETWORK / UPSTREAM / BAD_REQUEST.
- **Cancellation safety in IMAP/CalDAV clients.** A verb coroutine cancelled mid-`to_thread` orphans the worker thread, which can mutate `self._imap` / `self._principal` after the next call has acquired the lock. Race, not a deadlock. Fix is structural — the worker thread should observe a cancellation signal or the lock should bracket the entire to_thread span tighter.

---

## Notes on ordering

Bucket 1 is small and removes friction for everything after it. Bucket 2 is the bigger lift but unblocks GitHub/Linear/Notion/etc. Bucket 3 items are mostly independent — pull them off the shelf as users hit the rough edge.
