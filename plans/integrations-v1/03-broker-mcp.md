# 03 — MCP Broker

> Generic stdio host for any MCP server. Spawns `uvx`, `npx`, or any other launcher the catalog entry specifies, relays MCP frames between the app server and the subprocess.

---

## Purpose

Expose any Model Context Protocol (MCP) server as a Computron integration, with the same cred isolation and lifecycle guarantees as built-in brokers. The MCP broker is a **protocol adapter**, not a provider — one implementation handles GitHub, Home Assistant, Linear, Notion, Obsidian, and any future stdio MCP server.

The broker is a process that:

1. Spawns the MCP server as a child (`uvx <package>`, `npx <package>`, `node /path/to/server.js`, etc.) with cred env vars set.
2. Performs the MCP `initialize` handshake.
3. Calls `tools/list` to verify the server exposes at least one tool (this is the "verify" step).
4. Prints `READY\n` to stdout.
5. Relays MCP frames between its UDS socket (app-server facing) and the child's stdio.

---

## Code layout

```
brokers/
└── mcp_broker/
    ├── __init__.py
    ├── __main__.py        # entry: env → spawn → initialize → relay
    ├── _subprocess.py     # launch child, capture stdin/stdout/stderr
    ├── _protocol.py       # MCP frame encoding / decoding (JSON-RPC 2.0 over stdio with LSP-style headers)
    ├── _relay.py          # bidirectional passthrough with request-id tracking
    └── _verify.py         # tools/list check after initialize
```

Shares `brokers._common` with IMAP/CalDAV brokers for UDS server + ready-signaling + exit codes.

---

## Config at spawn time

Supervisor provides:

```
INTEGRATION_ID=github_main
BROKER_SOCKET=/run/cvault/brokers/github_main.sock
WRITE_ALLOWED=false                          # "true" or "false"; broker refuses non-read-only tools/call when false
MCP_COMMAND=uvx
MCP_ARGS=["github-mcp"]                      # JSON-encoded array
MCP_CWD=/home/computron                      # working dir for the subprocess
MCP_ENV_OVERRIDES={"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"}    # JSON object
MCP_INITIALIZE_TIMEOUT=30                    # seconds
```

Catalog entry supplies `MCP_COMMAND`, `MCP_ARGS`, `MCP_CWD`, and the list of env-var *names* to inject. The auth plugin's `ENV_INJECTION` populates the actual values from the decrypted blob.

---

## Startup sequence

```
1. Parse env; JSON-decode MCP_ARGS and MCP_ENV_OVERRIDES; parse WRITE_ALLOWED
2. Spawn MCP subprocess with:
   - stdin/stdout as pipes (MCP frames)
   - stderr captured and forwarded to the broker's stderr
   - env = clean minimal env + MCP_ENV_OVERRIDES
3. Send MCP initialize request, read response, verify protocol version compat
4. Send tools/list; require len(tools) >= 1 else exit 77 (treat missing tools as auth failure)
5. Build self._tool_is_read_only map from the returned tool annotations
6. Create UDS server at $BROKER_SOCKET
7. print("READY", flush=True)
8. Enter relay loop (with tools/call write-enforcement hook)
```

---

## Relay semantics

The MCP broker is mostly-thin — pure passthrough, with one policy hook for write-permission enforcement (see below):

- Every frame from the UDS client is forwarded to the MCP subprocess's stdin, **except** `tools/call` for a tool that's been classified as write, when `WRITE_ALLOWED=false` — those are refused locally.
- Every frame from the subprocess's stdout is forwarded back to the UDS client.
- JSON-RPC request IDs are rewritten only enough to prevent collisions (we own a namespace; clients own theirs) and reversed on the way back.
- **Notifications** (MCP "progress" frames, log messages) are forwarded without response tracking.
- On `notifications/tools/list_changed` from upstream, the broker re-runs `tools/list`, updates its read-only map (below), then forwards the notification.

The broker does NOT translate MCP verbs to domain verbs. The app-server's MCP bridge code is responsible for turning an MCP tool into an agent-visible tool. That bridge lives outside the broker — see `05-api-and-client.md`.

---

## Tool-level write enforcement

The broker enforces `WRITE_ALLOWED` at the `tools/call` frame, mirroring how the email/calendar brokers enforce at verb dispatch. This makes the permission gate real — an agent with `bash-run` connecting directly to the broker's UDS cannot bypass it.

**At startup** (right after `initialize`, right after `tools/list` during the verify step), the broker builds an internal map of each tool's `readOnlyHint`:

```python
self._tool_is_read_only = {
    t["name"]: bool(t.get("annotations", {}).get("readOnlyHint", False))
    for t in tools_list_response["tools"]
}
```

Missing annotations are treated as write (fail-closed).

**On every `tools/call` frame** from the UDS client:

```python
if not self._write_allowed and not self._tool_is_read_only.get(tool_name, False):
    return jsonrpc_error(id, code=-32000,
                         message=f"tool '{tool_name}' requires write permission")
```

Rejected locally — the subprocess never sees the call.

**On `notifications/tools/list_changed`** from the subprocess, the broker re-runs `tools/list` and rebuilds the read-only map before forwarding the notification to the app server. New tools added upstream inherit the same read-only-hint logic.

**Permission toggle = broker respawn** (same as email/calendar brokers). The broker reads `WRITE_ALLOWED` from env at startup; flipping requires a fresh process. Supervisor's `set_permissions` RPC handles the restart.

The app-server MCP bridge (see `05-api-and-client.md`) additionally skips non-read-only tools at *registration* time — those tools don't appear in the agent's tool list at all when writes are disabled. That's UX + short-circuit, not security; the broker's dispatch-time check is what actually defends.

---

## MCP frame protocol

MCP uses JSON-RPC 2.0 over stdio with LSP-style framing:

```
Content-Length: NNN\r\n
\r\n
<NNN bytes of JSON>
```

We implement this in `_protocol.py`. On the UDS side, we use the same length-prefixed-JSON wire format as IMAP/CalDAV brokers (4-byte BE length + JSON body) so the app-server's `broker_client` is uniform across broker kinds. The `_relay.py` module bridges the two framings.

---

## Verify step

After `initialize`:

```python
response = await mcp.call("tools/list", {})
if len(response["tools"]) == 0:
    sys.exit(77)   # treat as auth failure; token likely invalid
```

Some MCP servers (notably GitHub's) return an empty tool list when the access token is invalid instead of erroring out. Treating empty → 77 catches this case.

---

## Shutdown semantics

On SIGTERM:

```
1. Stop accepting new UDS connections
2. Send JSON-RPC shutdown notification to the subprocess
3. Close stdin (subprocess should exit cleanly)
4. Wait up to 5s for subprocess exit
5. If still alive, SIGTERM the subprocess
6. Wait 2s more, then SIGKILL
7. Exit 0
```

---

## Dependencies

- Launchers installed in the container image: `uvx` (via `uv`), `npx` (via Node.js). See `08-container.md`.
- Python: stdlib `asyncio`, `json`. No new pip deps.
- Shared `brokers._common`.

---

## Security considerations

- **Subprocess runs as UID 1001 (broker), same as the MCP broker itself.** No further privilege drop; there's nowhere lower that still allows outbound network.
- **`MCP_ENV_OVERRIDES` never appears in argv.** Verified by `ps auxe` at runtime during tests.
- **No stdin from the app server.** UDS is the only input channel; subprocess stdin is controlled entirely by the broker.
- **Core dumps disabled** (inherited from supervisor's `preexec_fn`).
- **No host filesystem access beyond the container.** Containers already provide this; we don't add more.

The standing accepted risk: an MCP server can exfiltrate creds it was given, or network-attack upstreams it has access to. Mitigation is "user consented by installing it." P2 enhancement: per-integration iptables egress allowlist.

---

## Implementation milestones

1. `_protocol.py` — LSP framing + JSON-RPC 2.0, unit tests against recorded frames.
2. `_subprocess.py` — spawn + stdio plumbing, with a stub MCP server (Python script that implements `initialize` + `tools/list` + one tool).
3. `_relay.py` — bidirectional passthrough with ID rewriting.
4. `_verify.py` — initialize + tools/list + exit-code behavior.
5. End-to-end against `uvx github-mcp` in a dev container (manual smoke test).

---

## Testing notes

Strategy in [`09-testing.md`](09-testing.md). Component-specific scope:

- Tests spawn the real MCP broker subprocess, which in turn spawns `tests/fixtures/stub_mcp_server.py` (also a real subprocess). Two levels of process, real UDS between test and broker, real stdio pipes between broker and stub. The only thing not real is what's behind the stub (no actual GitHub API, etc.).
- Behaviors:
  - Happy path: stub returns two tools from `tools/list` (one with `readOnlyHint: true`, one without) → broker prints READY → tests invoke `tools/call` through the broker → responses round-trip.
  - Auth failure: stub configured with `STUB_MCP_AUTH_FAIL=1` → empty `tools/list` → broker exits 77.
  - Initialize timeout: `STUB_MCP_HANG=60` with `MCP_INITIALIZE_TIMEOUT=2` → broker exits with a timeout error.
  - Shutdown: SIGTERM to broker → broker sends JSON-RPC `shutdown`, closes stub's stdin, stub exits; broker exits 0 within the 5 s + 2 s grace window.
  - Request-ID rewriting: concurrent test calls with overlapping IDs from different clients → broker namespaces them and restores on response.
  - **Write enforcement**: broker spawned with `WRITE_ALLOWED=false` and stub returning one read-only + one write-capable tool. `tools/call` for the read-only tool succeeds; `tools/call` for the write tool returns a JSON-RPC error locally and the stub observes zero matching calls on stdin. Respawn with `WRITE_ALLOWED=true` → both tools succeed.
  - **Tools-list-changed refresh**: initial `tools/list` has one read-only tool. Stub sends `notifications/tools/list_changed`; next `tools/list` response contains a new write tool. With `WRITE_ALLOWED=false` the new tool is still refused. With `WRITE_ALLOWED=true` it succeeds. (Stub configurable via a control verb over a side channel, or by restarting the stub subprocess mid-test.)
- `uvx github-mcp` against real GitHub is a manual PR-checklist smoke test, not CI.
- Pure-unit coverage (`@pytest.mark.unit`): LSP framing (Content-Length headers, multi-byte UTF-8 lengths) and JSON-RPC ID rewriting — both pure byte-manipulation worth isolating.

---

## Component-local open items

- **Resource lists / prompts.** MCP has more surface area than just `tools/*`. v1 relays everything but only exercises `tools/list` and `tools/call`. Later we may want first-class resource/prompt support — relay already supports it, UI doesn't yet.
- **Streaming responses.** Some MCP tools stream progress notifications. We forward them; whether the app server or agent surfaces them is out of scope here.
- **Streamable HTTP transport.** Deferred to P2. The broker would gain an `MCP_TRANSPORT=http` branch; same verify logic.
- **Tool-name collisions** across multiple MCP integrations (two GitHub integrations both exposing `create_issue`). Handled by the app-server side: each MCP tool is prefixed with the integration ID when registered. Not the broker's problem.
