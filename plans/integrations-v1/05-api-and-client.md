# 05 — App Server API + Broker Client

> Two halves of the app server's integration surface:
> (a) the REST API the UI talks to, and
> (b) the Python client tool handlers use to talk to brokers.

The app server runs as UID `computron` (1000). It never reads decrypted creds. Everything credential-adjacent flows through the supervisor's `app.sock` (for management) or directly to brokers (for tool calls).

---

## Code layout

```
server/
├── routes/
│   └── integrations.py     # /api/integrations/* handlers (aiohttp)
└── ...

broker_client/              # new top-level package
├── __init__.py             # facade — `from broker_client import call`
├── _resolve.py             # integration_id → broker socket, via supervisor
├── _rpc.py                 # length-prefixed JSON client, matches broker wire format
├── _errors.py              # custom exception hierarchy
└── types.py                # shared Pydantic models
```

---

## REST routes

All mounted under `/api/integrations/`. aiohttp handlers forward to the supervisor's `app.sock` for stateful ops, or to the catalog loader for read-only catalog calls.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/integrations` | List installed integrations with state, socket, and `write_allowed` (never cred values) |
| `POST` | `/api/integrations` | Add: validates form, POSTs blob to supervisor. Body includes `write_allowed` (default `false`) |
| `DELETE` | `/api/integrations/:id` | Remove: calls supervisor `remove` |
| `POST` | `/api/integrations/:id/verify` | Re-verify: calls supervisor `verify` (forces re-spawn) |
| `POST` | `/api/integrations/:id/reconnect` | Re-collect creds: same as add, but overwrites |
| `POST` | `/api/integrations/:id/enable` | Flip `disabled` → `pending` → `active` |
| `POST` | `/api/integrations/:id/disable` | SIGTERM broker, retain blob |
| `PATCH` | `/api/integrations/:id` | Update `label` and/or `write_allowed`. Neither touches creds or crypto — a `.meta` rewrite through supervisor's `update_label` / `set_permissions`. Toggling `write_allowed` triggers a tool-registry refresh on the app server. |
| `GET` | `/api/integrations/catalog` | List all catalog entries + states (filtered by category) |
| `GET` | `/api/integrations/catalog/:slug` | One entry merged with its auth plugin's `FIELDS` — this is what the wizard renders |

### Request/response shapes (sketch)

```jsonc
// GET /api/integrations
[
  {
    "id": "gmail_personal",
    "slug": "gmail",
    "label": "Larry's Gmail",
    "state": "active",
    "state_reason": null,
    "added_at": "2026-04-20T12:00:00Z",
    "tools_exposed": ["search_email", "fetch_message", "list_events", ...]
  },
  ...
]

// POST /api/integrations
// request
{
  "slug": "gmail",
  "user_suffix": "personal",
  "label": "Larry's Gmail",
  "write_allowed": false,
  "fields": {
    "email": "larry@gmail.com",
    "password": "abcd efgh ijkl mnop"
  }
}
// response (success)
{
  "id": "gmail_personal",
  "state": "active",
  "state_reason": null,
  "verify_ms": 1823
}
// response (auth fail)
409 Conflict
{
  "error": "AUTH",
  "state": "auth_failed",
  "state_reason": "IMAP LOGIN rejected (invalid credentials)"
}
```

### Validation pipeline

```
1. Load catalog entry for slug → resolve auth_plugin
2. Generate a pydantic model from plugin.FIELDS
3. Validate request.fields against it (required, regex, length, strip)
4. Normalize (apply `strip` char sets, trim)
5. Sanitize user_suffix (lowercase, [a-z0-9_-]+, max 48 chars)
6. Check for collisions; auto-suffix with _2, _3 as needed
7. POST to app.sock's add verb
```

Step 7's payload never contains raw user input that bypassed steps 1-4; app server is the single validation point.

### The brief-transit risk

The app server's HTTP handler parses the POST body (including the password) before forwarding to `app.sock`. Accepted risk per the main plan. Mitigation: hand the bytes off to `app.sock` as soon as pydantic validation returns, and zero the local variable. Not a guarantee but minimizes the window.

The **load-bearing** defense for this window is kernel-level ptrace restriction + container capability hygiene, asserted by the supervisor at startup (`01-supervisor.md` "Runtime hardening assertions" + `08-container.md` "Required container security flags"). With those in place, the agent's `run_bash_cmd` subprocess cannot read the app-server's memory even though they share a UID. Don't remove those hardenings on the assumption that the below hygiene rules are enough — they aren't.

### Logging hygiene (add / reconnect handlers)

The add and reconnect handlers touch plaintext credentials briefly before forwarding to the supervisor. Strict rules apply to this code path:

- **Never log request bodies.** aiohttp's default access log is fine (it records method + path + status, not the body). If custom request logging is added, verify it doesn't format `await request.json()` or `request.text()` anywhere.
- **Never log `os.environ`.** Not a cred vector for integrations specifically (creds arrive via HTTP body, not env), but the rule is universal so we don't have to reason about which processes are cred-touching on each audit.
- **Scrub traceback locals on cred-path exceptions.** If an exception escapes the add/reconnect handler, log it with `exc_info=True` but install a `logging.Filter` on the relevant logger that strips `locals()` from the frame summaries. The validated fields would otherwise appear in a traceback — exactly what we just spent effort keeping out of memory for longer than needed.
- **Scope cred references tightly.** Read the body, run pydantic, immediately forward to `app.sock`, `del` the local variable, let the handler return. The pydantic model instance shouldn't outlive a single scope.

None of these are load-bearing individually — they're hygiene. The kernel-level ptrace defense is what actually prevents exfiltration from the app server's memory.

---

## Broker client

Tool handlers use this. It's the ONLY place outside server/routes that talks to integrations.

```python
# tools/email/search.py
from broker_client import call, IntegrationNotConnected

async def search_email(integration_id: str, query: str) -> list[EmailHeader]:
    try:
        result = await call(
            integration_id=integration_id,
            verb="search_messages",
            args={"mailbox": "INBOX", "query": query, "limit": 50},
            kind_hint="imap",     # optional; disambiguates Gmail's IMAP vs CalDAV sockets
        )
    except IntegrationNotConnected as e:
        raise ToolError(f"Integration '{integration_id}' is not connected: {e.reason}")
    return [EmailHeader(**row) for row in result["messages"]]
```

### `call()` pipeline

```
1. Resolve integration_id → {socket, write_allowed} via supervisor's resolve verb (cached briefly)
2. If state != active → raise IntegrationNotConnected(state, reason)
3. Look up verb type in the broker-kind verb table (email/calendar tables in 02; MCP uses
   the requires_write recorded at bridge registration time).
   If type == "write" and write_allowed is False:
       raise IntegrationWriteDenied(integration_id, verb)
   **This check is belt-and-braces, not the security gate.** The broker itself enforces when
   spawned with WRITE_ALLOWED=false in its env (see 02-broker-email-calendar.md "About the
   Type column" and 03-broker-mcp.md "Tool-level write enforcement"). This client-side check
   exists to:
     (a) short-circuit denied writes before a wire round-trip,
     (b) give the agent a crisp, integration-aware error message instead of a generic
         WRITE_DENIED frame from the broker, and
     (c) catch programming errors (registry drift, stale cached state) early.
   A well-behaved agent won't hit this path — write tools are absent from its registry when
   write_allowed=false. An agent with `bash-run` that bypasses the registry and the client
   entirely is stopped by the broker.
4. Open UDS to broker socket
5. Send length-prefixed JSON: {id, verb, args}
6. Read response frame
7. On {error}, map code to exception:
   AUTH       → IntegrationAuthFailed  (and hint supervisor via events)
   NETWORK    → IntegrationNetworkError
   UPSTREAM   → IntegrationUpstreamError
   BAD_REQUEST → ProgrammingError
8. Return result
```

### Verb classification table

Built-in brokers ship a const table in `broker_client._verb_types`:

```python
_VERB_TYPES: dict[str, dict[str, Literal["read", "write"]]] = {
    "email": {
        "list_mailboxes":   "read",
        "search_messages":  "read",
        "fetch_message":    "read",
        "fetch_headers":    "read",
        "fetch_attachment": "read",
        "flag_message":     "write",
        "move_message":     "write",
        "send_message":     "write",
    },
    "calendar": {
        "list_calendars": "read",
        "list_events":    "read",
        "get_event":      "read",
        "create_event":   "write",
        "update_event":   "write",
        "delete_event":   "write",
    },
}
```

Kept in sync with the tables in `02-broker-email-calendar.md` — a unit test diffs the two at build time.

For MCP tools, `requires_write` is stored on each registered tool by the MCP bridge (see below).

### Connection pooling

One UDS connection per broker, held in the client's `ConnectionPool`. Brokers are long-lived; the app server keeps connections open across requests. Reconnect if the broker was restarted (supervisor's resolve verb returns a new socket path on restart).

### Caching

`resolve()` results cached for 500ms. Short enough to catch restarts, long enough to avoid hammering the supervisor on a tool call burst.

---

## Dynamic tool registry

When integrations change (add / remove / state transitions / `write_allowed` flip), the app server refreshes the agent's tool registry. This refresh does **two** things:

1. **Rewrites descriptions** of always-present read tools (`search_email`, `list_events`, …) so the list of available `integration_id` values is current.
2. **Adds or removes write-capable tools** based on the current `write_allowed` values. If no connected integration allows writes for a given verb, the tool is not registered at all — the agent never sees it.

```python
# called on supervisor state-change notifications
async def refresh_tool_registry():
    integrations = await list_integrations()

    email_ids    = [i.id for i in integrations if i.kind == "email_calendar" and i.state == "active"]
    email_write_ids = [i.id for i in email_ids_active if i.write_allowed]

    # Read tools — always registered while any active integration exists.
    tool_registry.upsert("search_email", build_search_email_desc(email_ids))
    tool_registry.upsert("list_events",  build_list_events_desc(email_ids))
    # … other read tools

    # Write tools — registered only when at least one integration has write_allowed=true.
    if email_write_ids:
        tool_registry.upsert("flag_message",  build_flag_message_desc(email_write_ids))
        tool_registry.upsert("move_message",  build_move_message_desc(email_write_ids))
        tool_registry.upsert("create_event",  build_create_event_desc(email_write_ids))
        tool_registry.upsert("update_event",  build_update_event_desc(email_write_ids))
        tool_registry.upsert("delete_event",  build_delete_event_desc(email_write_ids))
    else:
        tool_registry.remove("flag_message", "move_message",
                             "create_event", "update_event", "delete_event")

    # MCP tools refreshed by the MCP bridge (see below).
```

Supervisor pushes state-change events (including `write_allowed` flips from `set_permissions`) over a long-lived `app.sock` connection (subscribe verb). App server subscribes once at startup.

A one-line hint in the agent's system prompt covers the UX gap created by hiding write tools:

> Some integrations default to read-only. If the user asks for an action that would require writes (sending email, creating or deleting calendar events, destructive repo operations), let them know they can enable writes from Settings → Integrations.

---

## MCP tool bridging

The app server turns MCP tool declarations into first-party agent tools. The bridge (`server/mcp_bridge.py`, new file) handles per-tool registration and the UX/short-circuit layer of the permission gate.

1. Query each `mcp_subprocess` integration's broker with `tools/list` on startup + on refresh.
2. For each returned tool:
   ```
   requires_write = not tool.annotations.get("readOnlyHint", False)
   # missing annotation → fail closed; destructiveHint implies write but readOnlyHint is the
   # authoritative opt-in to being treated as read.

   if requires_write and not integration.write_allowed:
       continue   # do not register — agent never sees it
   tool_registry.register(
       name=f"{integration.id}.{tool.name}",
       handler=passthrough_via_broker_client(integration.id, tool.name),
       requires_write=requires_write,   # stashed so broker_client can short-circuit
   )
   ```
3. Re-run the registration scan whenever:
   - An integration transitions to/from `active`.
   - `write_allowed` flips (via supervisor's `set_permissions` event — which also restarts the broker, see below).
   - The broker reports a `notifications/tools/list_changed` MCP event (tools added/removed upstream).

**The broker is still the security gate.** The bridge skipping non-read-only tools at registration time is a UX/short-circuit layer — a well-behaved agent never sees those tools. But the MCP broker itself enforces per-`tools/call` (see `03-broker-mcp.md` "Tool-level write enforcement"); a `bash-run`-capable agent that connects directly to the broker's UDS is refused there. Supervisor's `set_permissions` both restarts the broker with the new `WRITE_ALLOWED` env and fires the state-change event that triggers step 3 above — the two layers move together.

---

## Dependencies

- aiohttp (already present).
- Pydantic (already present).
- No new deps.

---

## Implementation milestones

1. `broker_client/_rpc.py` — length-prefixed JSON client + connection pool. Unit tests against a stub UDS.
2. `broker_client/_resolve.py` + caching.
3. aiohttp routes for all endpoints in the table above.
4. `server/mcp_bridge.py` — dynamic tool registration.
5. Tool description refresh on supervisor state-change subscription.
6. End-to-end: UI can add Gmail, tool can `search_email(integration_id, query)`.

---

## Testing notes

Strategy in [`09-testing.md`](09-testing.md). Component-specific scope:

- **`broker_client`** is the one place where full integration-style tests would be overkill; the real value is the client's own logic. Use `tests/fixtures/stub_broker.py` (in-process UDS server) to exercise:
  - Write-verb gate: `write_allowed=false` + write verb → `IntegrationWriteDenied` raised before the UDS is opened.
  - Error mapping: stub returns each of `AUTH` / `NETWORK` / `UPSTREAM` / `BAD_REQUEST` → correct exception class raised.
  - Resolve cache: second `call()` within 500 ms of the first doesn't re-hit `app.sock` (assertable by pointing resolve at a counting stub).
  - Pool reconnect: stub restarts on a new socket path → broker_client picks up the new path on next resolve miss.
- **App-server routes** use `aiohttp.test_utils` with a **real supervisor process** and `FakeBroker` children, spun up in a session fixture (cheap once; reused across the route-test module). Tests exercise the full HTTP → app.sock → supervisor → broker path.
  - Happy `POST /api/integrations` → `active` returned.
  - Auth failure (`FAKE_AUTH_FAIL=startup`) → `409` with `state: auth_failed, state_reason: ...`.
  - `PATCH write_allowed=true` → response 200, subsequent `GET` reflects the flag, state-change event fires through the subscribe channel.
  - `GET` payloads never contain any secret-bundle field (regression guard: assert on a denylist).
- **MCP bridge** tests use a real MCP broker + stub MCP server:
  - `readOnlyHint=true` tool → registered regardless of `write_allowed`.
  - No-annotation tool → treated as write, skipped when `write_allowed=false`, registered when flipped to `true`.
  - Flipping `write_allowed` re-runs the registration scan (assertable via the registry's upsert/remove counters).
- Pure-unit coverage (`@pytest.mark.unit`): `_VERB_TYPES` diffed against the tables in `02-broker-email-calendar.md` (parser-level test that fails loud on drift); catalog-entry pydantic validation; route request-body pydantic validation.

---

## Component-local open items

- **Rate limiting.** A rogue tool chain could hammer a broker. v1: no limiting; relying on the broker's own upstream handling. v2: per-broker concurrency cap in `broker_client`.
- **Streaming responses.** Some future tools might want streaming (CalDAV sync, MCP progress events). Wire format is request/response today. Extension: a separate `stream` frame kind that supervises the in-flight request. Deferred.
- **Error telemetry.** When `IntegrationAuthFailed` fires from a tool call, we want the UI to notice without a manual refresh. Done via the state-change subscription feeding a Server-Sent-Events endpoint. Wire into the existing UI event bus.
