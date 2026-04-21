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
1. Parse env; JSON-decode MCP_ARGS and MCP_ENV_OVERRIDES
2. Spawn MCP subprocess with:
   - stdin/stdout as pipes (MCP frames)
   - stderr captured and forwarded to the broker's stderr
   - env = clean minimal env + MCP_ENV_OVERRIDES
3. Send MCP initialize request, read response, verify protocol version compat
4. Send tools/list; require len(tools) >= 1 else exit 77 (treat missing tools as auth failure)
5. Create UDS server at $BROKER_SOCKET
6. print("READY", flush=True)
7. Enter relay loop
```

---

## Relay semantics

The MCP broker is deliberately thin:

- Every frame from the UDS client is forwarded to the MCP subprocess's stdin.
- Every frame from the subprocess's stdout is forwarded back to the UDS client.
- JSON-RPC request IDs are rewritten only enough to prevent collisions (we own a namespace; clients own theirs) and reversed on the way back.
- **Notifications** (MCP "progress" frames, log messages) are forwarded without response tracking.

The broker does NOT translate MCP verbs to domain verbs. The app-server's MCP bridge code is responsible for turning an MCP tool into an agent-visible tool. That bridge lives outside the broker — see `05-api-and-client.md`.

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

- Unit tests use a stub MCP server written in Python that speaks the protocol in-process (no subprocess). Keeps tests fast and deterministic.
- Per project memory: **no integration tests**. The `uvx github-mcp` smoke test is manual, not in CI.

---

## Component-local open items

- **Resource lists / prompts.** MCP has more surface area than just `tools/*`. v1 relays everything but only exercises `tools/list` and `tools/call`. Later we may want first-class resource/prompt support — relay already supports it, UI doesn't yet.
- **Streaming responses.** Some MCP tools stream progress notifications. We forward them; whether the app server or agent surfaces them is out of scope here.
- **Streamable HTTP transport.** Deferred to P2. The broker would gain an `MCP_TRANSPORT=http` branch; same verify logic.
- **Tool-name collisions** across multiple MCP integrations (two GitHub integrations both exposing `create_issue`). Handled by the app-server side: each MCP tool is prefixed with the integration ID when registered. Not the broker's problem.
