# 01 — Broker Supervisor

> The only long-running root-adjacent process in the system. Owns the master key, the ciphertext, and every broker's lifecycle. Runs as UID `broker` (1001) after entrypoint hands off.

---

## Linux & Unix primitives used in this document

Plain-English glossary — no Linux background assumed. Skim on first read, refer back when a term shows up.

- **UID / GID (user ID / group ID).** A numeric identity for a Linux user or group. Every file and every running process has an owner identified by these numbers. Two UIDs matter here: `computron` (1000) for the app server + agent, and `broker` (1001) for everything that ever touches a credential. The kernel enforces file access by UID/GID — a process running as one UID cannot read a file owned by another if the permission bits forbid it.
- **PID (process ID).** Every running process has a unique number assigned by the kernel.
- **`fork` + `exec`.** How Unix creates a new program. `fork` clones the current process; `exec` replaces the clone's memory image with the target program. Python's `asyncio.create_subprocess_exec` wraps both.
- **Signals (`SIGTERM`, `SIGKILL`, `SIGCHLD`).** Tiny kernel-delivered messages to a process. `SIGTERM` = please exit cleanly (catchable). `SIGKILL` = die immediately (uncatchable). `SIGCHLD` = one of your children just exited; you should call `waitpid` to collect its exit status — otherwise it lingers as a "zombie" entry in the process table.
- **`waitpid` / `proc.wait()`.** The syscall (and Python wrapper) a parent uses to collect a dead child's exit status. Required to avoid zombies. The supervisor has one `await proc.wait()` task per broker.
- **stdin / stdout / stderr.** Three standard byte streams every process inherits. The supervisor reads a broker's stdout to detect the `READY\n` sentinel; it forwards the broker's stderr to container logs.
- **Pipe.** An unnamed one-way byte channel between two related processes, typically used to wire a child's stdout to the parent's reading end.
- **Unix domain socket (UDS).** An IPC endpoint that looks like a file on disk. Same API surface as TCP sockets, but local-only: one process listens on a path, others connect by path. Used here for supervisor ↔ app-server (`app.sock`) and broker ↔ app-server (`<id>.sock`) RPC.
- **`SO_PEERCRED`.** A UDS socket option that lets the listening side read the connecting process's UID/GID/PID directly from the kernel. We use it to refuse any connection that isn't from the `computron` UID.
- **tmpfs.** An in-memory filesystem. Files written there never reach disk and vanish on reboot. `/run/cvault/` is tmpfs so stale UDS socket files don't persist across container restarts.
- **File modes `0600` / `0700` (octal Unix permissions).** `0600` = owner can read and write, no one else can do anything. `0700` = owner can read/write/execute (for a directory, "execute" is what lets you enter or list it). The vault directory is `0700 broker`, so the agent (UID `computron`) literally can't `ls` it.
- **Atomic write (`tmp + fsync + rename`).** Standard durable-update recipe. Write new content to `foo.tmp`, `fsync` to flush it to disk, then `rename("foo.tmp", "foo")` — `rename` inside a single filesystem is atomic, so readers always see either the old file or the new one, never a half-written mess. Both `.enc` and `.meta` writes follow this pattern.
- **`preexec_fn`.** Python `subprocess` hook that runs inside the child process between `fork` and `exec`. We use it to disable core dumps (`ulimit -c 0`) and drop supplementary groups (`setgroups([])`) before the broker's code starts — so a broker crash can't leak credentials to a core file.
- **`/proc/<pid>/environ`.** Kernel interface exposing a process's environment variables as a single null-delimited file, mode `0400` owner. A different UID cannot read it.
- **`ptrace`.** A Linux system call used by debuggers (gdb, strace) to read another process's memory, attach to it, or step through its code. It's also the obvious way a malicious same-UID process could snoop on another process's RAM. The kernel gates who can call it on whom — see `ptrace_scope` and `CAP_SYS_PTRACE` below.
- **`kernel.yama.ptrace_scope`.** A kernel sysctl at `/proc/sys/kernel/yama/ptrace_scope` with four values:
  - `0` — unrestricted; any process can `ptrace` any other at the same UID.
  - `1` — restricted; a process can only `ptrace` its own direct descendants (e.g. a parent can trace its children, but a child cannot trace its parent). **This is the Linux default on Debian, Ubuntu, Fedora, RHEL.**
  - `2` — admin-only; only root / `CAP_SYS_PTRACE` processes can `ptrace`.
  - `3` — disabled entirely; no `ptrace` possible.
- **`CAP_SYS_PTRACE`.** One of Linux's "capabilities" — a split of root's privileges into individually-grantable pieces. A process holding `CAP_SYS_PTRACE` can call `ptrace` on any process regardless of UID *and* regardless of `ptrace_scope`. The capability overrides the scope check. So capability hygiene (`--cap-drop`) matters independent of `ptrace_scope`.
- **`no-new-privileges`.** A process flag (set via `prctl(PR_SET_NO_NEW_PRIVS)` or, in containers, `--security-opt=no-new-privileges`) that prevents the process and all its descendants from ever *gaining* privileges via setuid binaries, file capabilities, or similar. With it set, a capability set can only shrink over exec, never grow.

### Crypto terms (not Linux, but used here)

- **AES-256-GCM.** Authenticated encryption with a 32-byte key, a 12-byte nonce, the plaintext, and optional AAD. Returns ciphertext plus a 16-byte auth tag. Decryption fails if any byte of input or AAD has been tampered with.
- **Nonce.** Number-used-once. Must be unique per encryption under the same key. We generate a fresh random one per write and store it alongside the ciphertext.
- **AAD (additional authenticated data).** Bytes covered by the auth tag but not encrypted. We pass the integration ID as AAD — prevents an attacker with file-write access from silently swapping `id1.enc` into `id2.enc` and having it decrypt.

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
├── _store.py              # atomic reads/writes for <id>.enc and <id>.meta
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

Single AEAD, one master key. Encrypts only the **secret bundle** (auth field values collected from the user).

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_PATH  = Path("/var/lib/computron/vault/.master-key")

def load_or_init_master_key() -> bytes:
    """32 bytes. Creates on first boot, 0600 broker:broker."""

def encrypt_secrets(integration_id: str, secrets: dict) -> bytes:
    """version-byte || nonce(12) || aesgcm.encrypt(json(secrets), aad=id)"""

def decrypt_secrets(integration_id: str, data: bytes) -> dict:
    """Reverses encrypt_secrets. Raises on auth-tag mismatch."""
```

- Version byte = `0x01` for v1. Reserved so a future scheme can coexist.
- Nonce is random per write. Never reused.
- AAD = integration ID bytes. Binds the blob to its filename.
- **Zeroize on best effort.** Decrypted bytes held in `bytearray`, overwritten after use. Not a hard guarantee — Python GC may retain copies — but worth the few lines.

---

## Storage (`_store.py`)

Two files per integration under `/var/lib/computron/vault/creds/`, both `0600 broker:broker`:

```
<id>.enc    version(1) || nonce(12) || ciphertext+tag    — AES-GCM over the secret bundle
<id>.meta   plaintext JSON                               — non-secret metadata
```

`.meta` schema (Pydantic):

```python
class IntegrationMeta(BaseModel):
    version: int = 1
    id: str
    slug: str                  # catalog entry slug, e.g. "gmail"
    kind: str                  # "email_calendar" | "mcp_subprocess"
    label: str
    write_allowed: bool = False
    added_at: datetime
    updated_at: datetime
```

APIs:

```python
def read_meta(id) -> IntegrationMeta
def write_meta(meta) -> None             # atomic: tmp + fsync + rename
def read_secrets(id) -> dict             # calls decrypt_secrets
def write_secrets(id, secrets) -> None   # atomic: .enc.tmp + fsync + rename
def delete(id) -> None                   # removes both files

def list_integrations() -> list[IntegrationMeta]
    """Enumerate *.meta — never decrypts. Used by list/resolve and by startup."""
```

Startup assertion: an `.enc` without a matching `.meta` (or vice versa) logs a warning and is skipped. Prevents partial-write states from becoming ghosts in the registry.

Toggling `write_allowed` only rewrites `.meta`. The master key is never loaded on that path.

---

## Spawn path (`_spawn.py`)

```python
async def spawn_broker(
    integration_id: str,
    meta: IntegrationMeta,
    blob: dict,
    catalog_entry: CatalogEntry,
) -> BrokerHandle:
    env = _build_env(meta, blob, catalog_entry)   # ENV_INJECTION fields from blob + WRITE_ALLOWED from meta
    cmd = catalog_entry.broker_cmd                # e.g. ["python", "-m", "brokers.email_broker"]
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
- **`WRITE_ALLOWED` env is authoritative for broker-side permission enforcement.** `_build_env` always sets `WRITE_ALLOWED=true` or `WRITE_ALLOWED=false` (never absent). The broker reads it at startup; flipping requires a respawn via `set_permissions` (see `app.sock` RPC table).

---

## Lifecycle (`_lifecycle.py`)

State machine from `plan.md`. The supervisor is **not** in the RPC path between the app server and brokers — it never sees a tool call's request or response. State transitions are driven by two sources only:

- **Process events.** `asyncio.create_task(proc.wait())` per broker → SIGCHLD-like callback that flips state based on exit code: `77 → auth_failed`; any other nonzero → `error` (with backoff restart); `0` → `disabled` if user-initiated, otherwise `error`.
- **User actions via `app.sock`.** `verify` / `reconnect` / `disable` / `enable` / `remove` / `set_permissions` / `update_label`.

### How broker-observed errors reach the state machine

Brokers talk directly to the app server over their own UDS; the supervisor has no hook into that conversation. Errors flow into the state machine via the **process** channel, not the RPC channel:

- **Transient error** (one flaky upstream call, one reconnect blip). Broker responds to the pending RPC with `{"error": {"code": "..."}}`, stays alive, state stays `active`. The app server surfaces the error to the agent as a single failed tool call.
- **Persistent auth failure.** Per `02-broker-email-calendar.md` and `03-broker-mcp.md`, after N consecutive auth-rejections the broker replies to its pending RPC (so the current call returns a meaningful error) and then **exits with code 77**. Supervisor's `proc.wait()` resolves, state → `auth_failed`. No restart.
- **Persistent non-auth failure** (upstream dead, repeated network failures exhausting the broker's internal retries). Broker exits with code `1`. Supervisor flips state → `error` and schedules a backoff restart (1 s, 5 s, 30 s, 5 m).

This keeps the supervisor simple: it watches exit codes, not wire traffic. It also means a broker can't get "stuck" in an inconsistent state where the app server sees auth errors forever but the supervisor still thinks the integration is healthy — the broker exits, and the state machine catches up.

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
| `list` | `{}` | `[{id, slug, kind, label, state, write_allowed, socket}, …]` — reads `.meta` only, no crypto |
| `add` | `{provider_slug, user_suffix, auth_blob, label, write_allowed}` | `{id, state, socket}` |
| `verify` | `{id}` | `{state, last_error?}` (re-spawns broker) |
| `reconnect` | `{id, auth_blob}` | same as `add` but overwrites existing `.enc` (preserves `.meta` except `updated_at`) |
| `enable` | `{id}` | `{state}` |
| `disable` | `{id}` | `{state}` (SIGTERM broker, retain `.enc` + `.meta`) |
| `remove` | `{id}` | `{}` (SIGTERM + delete `.enc` + `.meta` + rm socket) |
| `set_permissions` | `{id, write_allowed}` | `{write_allowed}` — rewrites `.meta`, SIGTERMs the broker, respawns it with the new `WRITE_ALLOWED` env flag. Integration briefly goes `active → pending → active` (~1–3 s reconnect). State-change events fire at each transition, so the app server's tool registry refreshes automatically. **The restart is what makes the permission gate a real enforcement point** — the broker itself rejects write verbs when the env flag is false, defeating a direct-UDS bypass. |
| `update_label` | `{id, label}` | `{label}` — rewrites `.meta`. |
| `resolve` | `{id}` | `{socket, write_allowed}` — used by app server to locate broker for tool calls and check permissions |

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
2. Assert kernel.yama.ptrace_scope >= 1 AND CAP_SYS_PTRACE not in effective caps
   (see "Runtime hardening assertions" below for what these defend against)
3. load_or_init_master_key()
4. Load catalog entries, load auth plugins
5. mkdir /run/cvault/brokers/ (tmpfs)
6. Bind app.sock with SO_PEERCRED access check
7. For each <id>.meta in creds/:
     - Assert matching <id>.enc exists; warn+skip if not.
     - Read meta (plaintext). If state is not `disabled`:
         read_secrets() → decrypt, spawn broker (state = pending → active/error).
8. Start the attachments-dir GC task: every 60 s, walk /run/cvault/attachments/ and unlink files older than 5 min (leaked-handoff cleanup — see `02-broker-email-calendar.md` "Attachments").
9. Enter event loop (accept app.sock connections, watch broker processes)
```

---

## Runtime hardening assertions (ptrace defenses)

There's a narrow window where a user's credential lives briefly in the **app-server** process's memory — while the add-integration HTTP handler parses the POST body and forwards it to `app.sock`. The app server runs as UID `computron`, the same UID as the agent's `run_bash_cmd` tool. A `run_bash_cmd` subprocess is a child of the app server; in principle it could call `ptrace` on its parent to snapshot that memory during the window. Two kernel-level defenses block this, and the supervisor asserts both at startup so we fail loud rather than running silently-insecure.

```python
def _assert_ptrace_restricted() -> None:
    """Fail if kernel.yama.ptrace_scope is 0 (same-UID siblings can read each other's memory)."""
    try:
        scope = int(Path("/proc/sys/kernel/yama/ptrace_scope").read_text().strip())
    except (FileNotFoundError, ValueError):
        # Some kernels omit Yama; the CAP_SYS_PTRACE drop below is the backstop.
        return
    if scope < 1:
        sys.exit(
            "kernel.yama.ptrace_scope is 0 — same-UID processes can read each other's "
            "memory. Set to 1 (default on most distros) or run with --cap-drop=SYS_PTRACE "
            "and --security-opt=no-new-privileges. Refusing to start."
        )

def _assert_no_ptrace_cap() -> None:
    """Fail if the supervisor's own effective caps include CAP_SYS_PTRACE."""
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("CapEff:"):
            caps = int(line.split()[1], 16)
            if caps & (1 << 19):   # CAP_SYS_PTRACE is bit 19 in the capability bitmap
                sys.exit(
                    "Supervisor has CAP_SYS_PTRACE in its effective capability set. "
                    "Run the container with --cap-drop=ALL (or at least --cap-drop=SYS_PTRACE). "
                    "Refusing to start."
                )
            return
```

What each check buys, in plain terms:

- **`ptrace_scope >= 1`** — this kernel setting decides whether one process can attach to another at the same UID. At `1` (the default on Debian/Ubuntu/Fedora/RHEL) a child can only attach to its own descendants, so a `run_bash_cmd` subprocess *cannot* attach to the app server (its parent). At `0`, it can. The check refuses to start if the container's kernel is configured to `0` — that would silently undo the cred-transit protection.
- **No `CAP_SYS_PTRACE`** — `ptrace_scope` doesn't apply to processes that hold the `CAP_SYS_PTRACE` capability; those override it. We drop all caps at the container level (`08-container.md`), and this supervisor-side check verifies the drop actually happened. If a future container config misses the drop, this assertion catches it before any integration goes active.

Both assertions run right after the vault-perms check in the startup sequence. Either failing aborts the process, which under Option-A recovery aborts the container — the operator sees the error on the next restart.

**Scope note:** these protect the *app server's* credential-transit window, not the supervisor itself. The supervisor runs as UID `broker`, a different UID from the agent's, so it's already insulated from `ptrace` by the UID boundary. The supervisor is just the natural place to check the system-wide settings because it's the security-load-bearing process and fails the container fast if things are wrong.

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
5. Real broker integration (via `02-broker-email-calendar.md`).
6. Restart/backoff behavior under induced crashes.
7. First-boot + warm-boot (existing vault) smoke tests.

---

## Testing notes

Strategy and test-double contracts in [`09-testing.md`](09-testing.md). Component-specific scope for the supervisor:

- Supervisor tests are **integration-style** — a real supervisor process against a `tmp_path` vault, UDS at a path under `tmp_path`, and real `FakeBroker` subprocesses as children. No mocking of `subprocess`, `socket`, or filesystem calls.
- Behaviors to cover:
  - Happy add: `add` RPC → `.enc` + `.meta` written → broker spawned → `READY` → state `active`; socket responds.
  - Exit 77 on startup (`FAKE_AUTH_FAIL=startup`) → state `auth_failed`, no restart, `.enc` + `.meta` still present.
  - Exit 77 mid-session (`FAKE_AUTH_FAIL=midstream`) → state `auth_failed` on next `proc.wait()` fire.
  - Exit 1 with restart (`FAKE_CRASH_AFTER_N=1`) → supervisor honors 1 s / 5 s / 30 s / 5 m schedule; reaching `active ≥ 2 min` resets attempts.
  - Orphan `.enc` with no `.meta` at startup → WARN log, skipped, not spawned.
  - `set_permissions` RPC → `.meta` rewritten, master key never touched (assertable by patching `load_or_init_master_key` to raise and confirming the call path doesn't invoke it) **and the broker respawns with updated `WRITE_ALLOWED` env** (assertable by the `FakeBroker` PID changing and `/proc/<new-pid>/environ` showing the new flag).
  - `SO_PEERCRED` refusal when `COMPUTRON_APP_UID` is set to something the test process isn't.
- Pure-unit coverage (`@pytest.mark.unit`): `encrypt_secrets` / `decrypt_secrets` round-trip + tamper; `IntegrationMeta` pydantic validation; frame encode/decode edge cases.
- Never spawns real IMAP / HTTPS / MCP subprocesses — those belong to broker tests.

---

## Deviations from standard Linux practice

Places where this design knowingly departs from the textbook answer, and why.

- **Master key stored as a plain file on a persistent volume.** Standard hardening for a long-lived secret is the Linux kernel keyring, a TPM, or an external KMS. We use a regular file (`/var/lib/computron/vault/.master-key`, `0600 broker`) because (a) we target portable container deployments with no assumption about host facilities and (b) `plan.md` has explicitly accepted "backup of `computron_state` leaks the key" as a non-goal. Revisit if we ever ship a Go CLI that can bootstrap against the host keyring.
- **Ready signal over stdout (`READY\n`) instead of `sd_notify`.** `systemd`'s notify protocol (`sd_notify(READY=1)` over a notify socket) is the conventional way a service says "I'm live." We don't run systemd inside the container and don't want to pull in `libsystemd`, so the supervisor reads the broker's stdout and matches `READY\n` as its first line. Brokers set stdout to line-buffered and must not print anything before the ready sentinel. Unconventional but small-and-obvious.
- **`preexec_fn` in subprocess spawn.** Python's `subprocess` docs warn that `preexec_fn` runs between `fork` and `exec` in the child and is "not thread-safe" — in a multi-threaded parent it can deadlock. The supervisor is a single-threaded asyncio loop, so this is safe in practice, but it is a known sharp edge. The alternative would be calling `prctl(PR_SET_DUMPABLE, 0)` / `setrlimit` via `ctypes` from the parent and relying on inheritance, which is worse ergonomically.
- **No per-broker mount namespace or `chroot`.** Brokers inherit the supervisor's full filesystem view. The textbook answer to "isolate a subprocess" is `unshare(CLONE_NEWNS)` + `pivot_root`, or a syscall-filtering sandbox. We rely on UID isolation + the `broker` user's lack of access to anything outside `/var/lib/computron/vault/` and `/run/cvault/`. Good enough for v1; revisit if we ever run untrusted broker binaries.
- **One supervisor process for everything (crypto + spawn + lifecycle).** A classic privilege-tier layout would split into (a) a root-kept keyring agent, (b) a non-root supervisor, (c) per-broker users. We collapsed to two tiers (`broker` / `computron`) because the only asset we're protecting is "the agent can't exfiltrate creds" and the second tier is already sufficient for that. Discussed in `plan.md`'s "Resolved design decisions."

---

## Component-local open items

- **Logging.** Supervisor logs to stderr (container captures). Broker stderr forwarded as-is. Structured (JSON) vs unstructured — defer to `08-container.md`.
- **Metrics / diagnostics endpoint.** Nice-to-have; deferred past v1.
- **Graceful master-key rotation.** Schema has a version byte; rotation command is P2.
- **Broker-spawn env: curated allow-list.** Today the supervisor copies its own `os.environ` wholesale when building the broker's env, then overlays protocol config + secret-bundle injections. That inherits whatever random vars happened to be set on the supervisor (and by extension, whatever the entrypoint set before `gosu broker`). When we harden the container, replace the wholesale copy with a curated allow-list (`PATH`, `HOME`, `SSL_CERT_FILE`, locale vars, and anything we specifically know a broker needs). Narrows the implicit surface and makes the spawn env auditable.
