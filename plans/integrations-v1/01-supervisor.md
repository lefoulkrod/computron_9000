# 01 — Broker Supervisor

> The only long-running root-adjacent process in the system. Owns the master key, the ciphertext, and every broker's lifecycle. Runs as UID `broker` (1001) after entrypoint hands off.

---

## Purpose

Replace the reference plan's vault daemon + separate supervisor with a **single process** that:

1. Manages the master key (generate on first boot, read on subsequent boots).
2. Encrypts/decrypts per-integration cred blobs.
3. Spawns one broker per integration, tracks lifecycle, restarts on crash.
4. Serves `/run/cvault/app.sock` so the app server can add/remove/verify/list integrations and resolve integration IDs to broker sockets.
5. Maintains the integration state machine (`pending` / `active` / `auth_failed` / `error` / `disabled`).

No network IO. No TLS. No HTTP. Just crypto + process control + UDS.

---

## Code layout

```
broker_supervisor/
├── __init__.py            # facade, re-exports from submodules
├── __main__.py            # entry point: `python -m broker_supervisor`
├── _crypto.py             # AES-256-GCM encrypt/decrypt, master-key lifecycle
├── _spawn.py              # fork+exec, env injection, stdout READY watcher
├── _lifecycle.py          # state machine, restart backoff
├── _registry.py           # in-memory table: id -> (pid, socket, state, etc.)
├── _app_sock.py           # UDS server handling /api/integrations/* requests
├── _auth_plugins.py       # loads auth_plugins/ modules (schemas only)
├── _catalog.py            # loads config/integrations_catalog/*.json
└── types.py               # Pydantic models — no internal deps
```

Internal imports follow the defining-submodule rule (`from broker_supervisor._crypto import ...`, not `from broker_supervisor import ...`).

---

## Crypto (`_crypto.py`)

Single AEAD, one master key, per-integration files.

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_PATH  = Path("/var/lib/computron/vault/.master-key")
_CREDS_DIR = Path("/var/lib/computron/vault/creds")

def load_or_init_master_key() -> bytes:
    """32 bytes. Creates on first boot, 0600 broker:broker."""

def encrypt_blob(integration_id: str, payload: dict) -> bytes:
    """version-byte || nonce(12) || aesgcm.encrypt(payload, aad=id)"""

def decrypt_blob(integration_id: str, data: bytes) -> dict:
    """Reverses encrypt_blob. Raises on auth-tag mismatch."""
```

- Version byte = `0x01` for v1. Reserved so a future scheme can coexist.
- Nonce is random per write. Never reused.
- AAD = integration ID bytes. Binds the blob to its filename.
- **Zeroize on best effort.** Decrypted bytes held in `bytearray`, overwritten after use. Not a hard guarantee — Python GC may retain copies — but worth the few lines.

---

## Spawn path (`_spawn.py`)

```python
async def spawn_broker(
    integration_id: str,
    blob: dict,
    catalog_entry: CatalogEntry,
) -> BrokerHandle:
    env = _build_env(blob, catalog_entry)   # from auth_plugin ENV_INJECTION
    cmd = catalog_entry.broker_cmd           # e.g. ["python", "-m", "brokers.imap_caldav"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
        preexec_fn=_harden,  # ulimit -c 0, setgroups([])
    )
    await _wait_for_ready(proc, timeout=30)
    return BrokerHandle(integration_id, proc, socket_path)
```

- **Env only, never argv.** `argv` is visible in `/proc/<pid>/cmdline`, world-readable by default.
- **No fork+setuid dance.** Supervisor is already UID 1001; spawned children inherit that.
- **`_wait_for_ready`** reads proc's stdout until `READY\n` or exit. Timeout → kill + `error`. Exit 77 → `auth_failed`. Other nonzero exit → `error`.
- Broker stdout beyond the first `READY\n` line is forwarded to container logs (stderr is always forwarded).

---

## Lifecycle (`_lifecycle.py`)

State machine from `plan.md`. Transitions driven by three sources:

- **Process events.** `asyncio.create_task(proc.wait())` per broker → SIGCHLD-like callback that flips state based on exit code.
- **RPC error replies.** When the app server calls a broker and the broker returns `{"error": {"code": "AUTH"}}`, supervisor flips `active → auth_failed`.
- **User actions via `app.sock`.** `verify` / `reconnect` / `disable` / `enable` / `remove`.

Auto-retry backoff for `error`:

```
attempts = [1s, 5s, 30s, 5m]
after attempts exhausted → stay in `error`, wait for manual Retry
```

Retries reset once broker reaches `active` for ≥ 2 minutes.

---

## In-memory registry (`_registry.py`)

```python
@dataclass
class IntegrationRecord:
    id: str
    state: State
    catalog_entry: CatalogEntry
    broker: BrokerHandle | None
    socket_path: Path         # /run/cvault/brokers/<id>.sock
    last_error: str | None
    state_changed_at: datetime
```

- Reconstructable from vault contents on supervisor restart. No persistent state of its own.
- Guard with an `asyncio.Lock` — all mutations serialize through one coroutine to avoid races between app-sock requests and process-event callbacks.

---

## `app.sock` RPC surface

Length-prefixed JSON frames over `/run/cvault/app.sock` (broker:computron 0660). SO_PEERCRED assertion: peer UID must be `computron`.

| Verb | Request | Response |
|---|---|---|
| `list` | `{}` | `[{id, kind, label, state, socket}, …]` |
| `add` | `{provider_slug, user_suffix, auth_blob, label}` | `{id, state, socket}` |
| `verify` | `{id}` | `{state, last_error?}` (re-spawns broker) |
| `reconnect` | `{id, auth_blob}` | same as `add` but overwrites existing blob |
| `enable` | `{id}` | `{state}` |
| `disable` | `{id}` | `{state}` (SIGTERM broker, retain blob) |
| `remove` | `{id}` | `{}` (SIGTERM + delete blob + rm socket) |
| `resolve` | `{id}` | `{socket}` — used by app server to locate broker for tool calls |

Wire format: `<4-byte BE length><JSON bytes>`. Trivial to parse, trivial to debug with `socat`.

---

## Dependencies

- Runtime: `cryptography` (already in `pyproject.toml`? — verify), `pydantic`, stdlib `asyncio`.
- At boot: entrypoint has already `chown`ed `/var/lib/computron/vault/` and `mkdir`ed `/run/cvault/` as tmpfs.
- Reads: `config/integrations_catalog/*.json` (bundled with the app image).
- Reads: `auth_plugins/*.py` (also bundled; imported dynamically).

---

## Startup sequence

```
1. Assert vault/ is owned by broker:broker at mode 0700 (refuse to start otherwise)
2. load_or_init_master_key()
3. Load catalog entries, load auth plugins
4. mkdir /run/cvault/brokers/ (tmpfs)
5. Bind app.sock with SO_PEERCRED access check
6. For each existing creds/<id>.enc:
     decrypt blob, spawn broker (state = pending → active/error based on outcome)
7. Enter event loop (accept app.sock connections, watch broker processes)
```

---

## Shutdown sequence (SIGTERM from entrypoint / container stop)

```
1. Stop accepting new app.sock connections
2. SIGTERM all brokers in parallel
3. waitpid with 10s grace, then SIGKILL stragglers
4. unlink sockets, close files
5. exit 0
```

---

## Implementation milestones

1. `_crypto.py` + test vectors (encrypt/decrypt round-trip; version mismatch; aad mismatch).
2. `_spawn.py` with a stub broker that just prints `READY` and sleeps (exercise the env-injection + ready path).
3. `_registry.py` + `_lifecycle.py` state transitions as a pure unit under `pytest` (no subprocess).
4. `_app_sock.py` with in-memory registry (no real brokers yet).
5. Real broker integration (via `02-broker-imap-caldav.md`).
6. Restart/backoff behavior under induced crashes.
7. First-boot + warm-boot (existing vault) smoke tests.

---

## Testing notes

- **Unit tests** must not spawn real IMAP or HTTPS — use stub brokers that simulate the stdout/exit-code protocol.
- **Integration tests** (if we have any) go behind `@pytest.mark.integration` and are not part of `just test-unit`.
- Per CLAUDE.md: all tests unit-only; no Ollama, no external network.

---

## Component-local open items

- **Logging.** Supervisor logs to stderr (container captures). Broker stderr forwarded as-is. Structured (JSON) vs unstructured — defer to `08-container.md`.
- **Metrics / diagnostics endpoint.** Nice-to-have; deferred past v1.
- **Graceful master-key rotation.** Schema has a version byte; rotation command is P2.
