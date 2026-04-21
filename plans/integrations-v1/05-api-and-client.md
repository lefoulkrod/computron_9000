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
| `GET` | `/api/integrations` | List installed integrations with state + socket (never cred values) |
| `POST` | `/api/integrations` | Add: validates form, POSTs blob to supervisor |
| `DELETE` | `/api/integrations/:id` | Remove: calls supervisor `remove` |
| `POST` | `/api/integrations/:id/verify` | Re-verify: calls supervisor `verify` (forces re-spawn) |
| `POST` | `/api/integrations/:id/reconnect` | Re-collect creds: same as add, but overwrites |
| `POST` | `/api/integrations/:id/enable` | Flip `disabled` → `pending` → `active` |
| `POST` | `/api/integrations/:id/disable` | SIGTERM broker, retain blob |
| `PATCH` | `/api/integrations/:id` | Update label only (not creds, not ID) |
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
1. Resolve integration_id → socket path via supervisor's resolve verb (cached briefly)
2. If state != active → raise IntegrationNotConnected(state, reason)
3. Open UDS to broker socket
4. Send length-prefixed JSON: {id, verb, args}
5. Read response frame
6. On {error}, map code to exception:
   AUTH       → IntegrationAuthFailed  (and hint supervisor via events)
   NETWORK    → IntegrationNetworkError
   UPSTREAM   → IntegrationUpstreamError
   BAD_REQUEST → ProgrammingError
7. Return result
```

### Connection pooling

One UDS connection per broker, held in the client's `ConnectionPool`. Brokers are long-lived; the app server keeps connections open across requests. Reconnect if the broker was restarted (supervisor's resolve verb returns a new socket path on restart).

### Caching

`resolve()` results cached for 500ms. Short enough to catch restarts, long enough to avoid hammering the supervisor on a tool call burst.

---

## Dynamic tool descriptions

When integrations change (add / remove / state transitions of interest), the app server refreshes the agent's tool registry so descriptions reflect current integrations.

```python
# called on supervisor state-change notifications
async def refresh_tool_descriptions():
    integrations = await list_integrations()
    email_ids = [i.id for i in integrations if i.kind == "imap_caldav" and i.state == "active"]
    tool_registry.update_description(
        "search_email",
        build_search_email_desc(email_ids),
    )
    # same for list_events, tools from MCP integrations, etc.
```

Supervisor pushes state-change events over a long-lived `app.sock` connection (subscribe verb). App server subscribes once at startup.

---

## MCP tool bridging

The app server turns MCP tool declarations into first-party agent tools:

1. Query each `mcp_subprocess` integration's broker with `tools/list` on startup + on refresh.
2. For each returned tool, register a dynamic tool in the agent registry with name `<integration_id>.<tool_name>` and pass-through handler that calls `tools/call` via `broker_client.call`.
3. On supervisor notification that an integration went active/inactive, re-scan its tools.

This MCP bridge lives in `server/mcp_bridge.py` (new file). Keeps the broker itself agnostic.

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

- Unit tests with a stub supervisor and stub brokers (both speak the wire format in-process).
- Per project memory: **no server integration tests** that require the real supervisor. Everything is mocked at the UDS layer.
- Route tests use `aiohttp.test_utils` with the stub supervisor.

---

## Component-local open items

- **Rate limiting.** A rogue tool chain could hammer a broker. v1: no limiting; relying on the broker's own upstream handling. v2: per-broker concurrency cap in `broker_client`.
- **Streaming responses.** Some future tools might want streaming (CalDAV sync, MCP progress events). Wire format is request/response today. Extension: a separate `stream` frame kind that supervises the in-flight request. Deferred.
- **Error telemetry.** When `IntegrationAuthFailed` fires from a tool call, we want the UI to notice without a manual refresh. Done via the state-change subscription feeding a Server-Sent-Events endpoint. Wire into the existing UI event bus.
