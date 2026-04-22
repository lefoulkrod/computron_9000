# 08 — Container Runtime

> What changes in the Dockerfile, entrypoint, and runtime volume layout to support the supervisor + brokers.

---

## Purpose

Make UID split real. Add the `broker` user, install MCP launchers (`uvx`, `npx`), wire the entrypoint to chown the vault subdir, and start the supervisor as UID 1001 while the app server continues to run as UID 1000.

This is the plumbing without which everything else doesn't work.

---

## Dockerfile changes

### Add the `broker` user

```dockerfile
RUN useradd --uid 1001 --no-create-home --shell /usr/sbin/nologin broker
```

Pinned at UID 1001 to align with host-side file ownership on volume mounts. Keep as a comment flagging this is load-bearing for persistence across image pulls.

### Ensure `gosu` and `tini` are installed

The entrypoint drops privilege for each long-running service (`gosu`) and runs under `tini` as PID 1 for zombie reaping and signal forwarding:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends gosu tini \
 && rm -rf /var/lib/apt/lists/*
```

### ENTRYPOINT under `tini`

```dockerfile
ENTRYPOINT ["tini", "--", "/app/container/entrypoint.sh"]
```

`tini` sits at PID 1, forwards signals (so `docker stop` flows a clean SIGTERM through), and reaps any stragglers the entrypoint script doesn't catch.

### Install MCP launchers

```dockerfile
# uvx comes with uv; project already uses uv for Python deps
# npx requires Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*
```

Keeps the image single-stage; added size ~70 MB compressed. Worth it — many high-value MCP servers (Notion, Linear, GitHub's official) are npm packages.

### Copy new packages in

Existing Dockerfile already handles `/app` — nothing new to do structurally. The new Python packages (`broker_supervisor/`, `brokers/`, `auth_plugins/`, `broker_client/`, `config/integrations_catalog/`) are in the repo and copied alongside existing code.

### Required container security flags

These flags are **not optional** — the supervisor asserts them at startup and refuses to boot if they aren't honored (see `01-supervisor.md` "Runtime hardening assertions"). Without them, a `run_bash_cmd` subprocess under the agent could in principle read the app-server's memory during the ~10 ms window where a user's fresh credential is being parsed from an HTTP POST body.

Required `docker run` flags:

```
docker run \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  ... \
  computron_9000:latest
```

Plain-English explanation of what each does:

- **`--cap-drop=ALL`** — Linux splits root's special privileges into individually grantable "capabilities" (bind-low-ports, change-UID, send-arbitrary-signals, ptrace-any-process, etc.). A container by default inherits a handful of them. `--cap-drop=ALL` removes them all; the container runs with the bare minimum a normal user gets. We don't need any of them — the UID split happens at entrypoint time via `gosu` (which uses `setuid`, already available to root *during* the brief root phase of the entrypoint, so it doesn't need runtime capabilities to drop privilege). The critical one we're dropping is **`CAP_SYS_PTRACE`**, which would otherwise let any process in the container attach to and read any other process's memory regardless of UID.
- **`--security-opt=no-new-privileges`** — A process flag that stops the process (and every descendant) from ever *gaining* new privileges. Normally a process can escalate by exec'ing a setuid binary (like `sudo`), which would grab root. With this flag, exec'ing such a binary silently loses the setuid effect — the capability set can only shrink across exec, never grow. Belt-and-braces against a future misconfiguration that accidentally installs a setuid binary; with this flag, the agent still can't use it to reacquire dropped caps.

Combined with the kernel's default `kernel.yama.ptrace_scope=1` (which prevents a child process from attaching to its parent regardless of UID), these flags make it impossible for `run_bash_cmd` to snapshot the app-server's memory.

`CAP_NET_BIND_SERVICE` is sometimes listed as "needed" for apps that bind ports below 1024. We don't — the app server binds port 8080, brokers use UDS paths, and the supervisor binds a UDS. Drop everything.

### Runtime check

The supervisor reads `/proc/sys/kernel/yama/ptrace_scope` and `/proc/self/status` at startup and exits with a clear error if either check fails. See `01-supervisor.md` "Runtime hardening assertions" for the assertion bodies.

---

## Entrypoint script

`container/entrypoint.sh` — launched by `tini` as PID 1, runs briefly as root, then backgrounds both services and fails-fast on either exit.

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. First-time volume prep (root).
VAULT=/var/lib/computron/vault
mkdir -p "$VAULT/creds"
chown -R broker:broker "$VAULT"
chmod 0700 "$VAULT" "$VAULT/creds"

# 2. Tmpfs for UDS sockets + attachment handoff.
RUN=/run/cvault
mkdir -p "$RUN/brokers" "$RUN/attachments"
chown broker:broker    "$RUN" "$RUN/brokers"
chown broker:computron "$RUN/attachments"   # shared handoff; computron group lets the app server read
chmod 0750 "$RUN" "$RUN/brokers"
chmod 0770 "$RUN/attachments"               # broker + computron both rwx; world 0

# 3. Start the broker supervisor as UID broker (1001) in the background.
gosu broker python -m broker_supervisor &
SUPERVISOR_PID=$!

# 4. Wait for app.sock to appear so the app server doesn't race the supervisor.
for i in {1..50}; do
  [ -S /run/cvault/app.sock ] && break
  sleep 0.1
done
if [ ! -S /run/cvault/app.sock ]; then
  echo "[entrypoint] supervisor failed to bind app.sock" >&2
  kill -TERM "$SUPERVISOR_PID" 2>/dev/null || true
  exit 1
fi

# 5. Start the app server as UID computron (1000) in the background.
gosu computron python -m main &
APP_PID=$!

# 6. Fail-fast: whichever service exits first brings the container down.
#    Docker's restart policy handles recovery (one supervisor crash = one
#    container restart = fresh state for everything).
wait -n "$SUPERVISOR_PID" "$APP_PID"
exit_code=$?

echo "[entrypoint] a service exited with code $exit_code; shutting down container" >&2
kill -TERM "$SUPERVISOR_PID" "$APP_PID" 2>/dev/null || true
sleep 2   # brief grace window before tini / the kernel take over
exit "$exit_code"
```

### Recovery posture

**Chosen for v1: container-level fail-fast.** Either service dying → entrypoint exits → Docker's restart policy brings the whole container back with fresh state.

- Supervisor binds `app.sock` before the app server starts → no race.
- Neither process is PID 1 (tini is). Both run as siblings of the entrypoint script, which waits on both.
- Bounce cost: ~2–5 s. In-flight HTTP requests drop; chat reconnects via the existing reconnect path.
- Explicitly rejected alternatives for v1:
  - **In-place supervisor restart (watchdog).** Keeps the app server alive across a supervisor crash but requires kill-and-respawn logic on the next supervisor's side to reclaim orphaned brokers. Revisit if supervisor crashes turn out to be frequent enough that app-server restarts hurt.
  - **s6-overlay or similar multi-service init.** Proper per-service supervision with restart policies. Overkill for two processes where a container restart is acceptable recovery.

---

## Volume layout confirmation

Existing volumes (from README):

- `computron_home` → `/home/computron`
- `computron_state` → `/var/lib/computron`

**No new volume in v1.** Vault subdir lives inside `computron_state`:

```
/var/lib/computron/                (computron:computron 0755)
├── conversations/                 (computron)
├── memory/                        (computron)
├── profiles/                      (computron)
├── goals/                         (computron)
└── vault/                         (broker:broker 0700)
    ├── .master-key
    └── creds/
```

Entrypoint handles the `chown` the first time (or after a `just reset` recreates the volume empty).

---

## README updates

Minimal. Add to the "Environment Variables" or "Data Persistence" section:

```
### Credential vault

Integrations (Gmail, GitHub, etc.) store their credentials in an encrypted
subdirectory of `computron_state`. The master key lives in the same volume;
if you back up or export `computron_state`, treat it like a password-manager
backup. To reset integrations without touching conversations:

    docker exec computron rm -rf /var/lib/computron/vault

Then restart.
```

No changes to the run commands themselves. No new `-v` flags.

---

## Justfile additions

```
# Reset just the credential vault, preserving conversations/memory/profiles.
reset-vault:
    podman exec computron rm -rf /var/lib/computron/vault
    podman exec computron bash -lc 'mkdir -p /var/lib/computron/vault/creds && chown -R broker:broker /var/lib/computron/vault && chmod 0700 /var/lib/computron/vault /var/lib/computron/vault/creds'
    just restart-app
```

Dev-workflow convenience only. Not shipped to users.

---

## Startup assertions (supervisor side)

The entrypoint sets up `vault/` correctly. The supervisor double-checks on its side — if the mode or ownership is wrong, refuse to start. This catches the "future image regression" scenario where someone accidentally breaks the chown step.

```python
# broker_supervisor/__main__.py
def _assert_vault_perms():
    st = os.stat("/var/lib/computron/vault")
    if st.st_uid != BROKER_UID or st.st_gid != BROKER_GID:
        sys.exit("vault/ not owned by broker:broker — refusing to start")
    if stat.S_IMODE(st.st_mode) != 0o700:
        sys.exit("vault/ mode is not 0700 — refusing to start")
```

---

## Logging

Everything ends up on the container's stderr, which Docker captures. There is no per-producer tagging at the container-runtime layer — **Docker does not prefix log lines**. Any `[component]` marker has to come from the producer's own `logging` formatter.

- **Supervisor.** Stdlib `logging` configured with a `[supervisor]` prefix.
- **Brokers.** Stdlib `logging` configured with a `[broker:<integration_id>.<kind>]` prefix. Broker stderr is inherited by the supervisor, which forwards it unchanged (no extra wrapping).
- **App server.** Uses the project's existing `logging` config. Lines appear as-is; no `[app]` prefix unless we add one there. Not scoped in this plan — outside the integrations surface.

Result in `docker logs computron` (or `just logs`):

```
2026-04-21 09:14:22 INFO aiohttp.access POST /api/integrations 201 1823ms    ← app server (no prefix)
[supervisor] 2026-04-21 09:14:22 add gmail_personal: encrypt ok, spawning broker
[broker:gmail_personal.imap] 2026-04-21 09:14:23 IMAP LOGIN ok, READY
[supervisor] 2026-04-21 09:14:23 state gmail_personal: pending -> active
```

Filter patterns (for later reference):

- Supervisor + brokers only: `docker logs -f computron 2>&1 | grep -E '^\[(supervisor|broker:)'`
- One broker: `grep '^\[broker:gmail_personal'`

No structured logging (no `structlog`) in v1 — plain stdlib `logging` with per-component formatters.

---

## Implementation milestones

1. Dockerfile: add `broker` user, install `gosu`, `tini`, and Node.js; set `ENTRYPOINT ["tini", "--", "/app/container/entrypoint.sh"]`.
2. `entrypoint.sh`: vault setup + dual-process launch with `wait -n` fail-fast.
3. Dev smoke test: `just dev` → supervisor starts → app server starts → `/api/integrations` returns `[]`.
4. Startup assertion + its failure modes (wrong ownership simulated by a test container).
5. README + justfile doc updates.

---

## Testing notes

- Hard to unit-test entrypoint bash; cover with a container-integration test in CI that boots the image and asserts processes + socket paths exist.
- Supervisor startup assertions are unit-testable with a mocked `os.stat`.
- No real cred flow tested at this layer — that's covered by supervisor/broker unit tests.

---

## Component-local open items

- **Image size.** Adding Node.js is ~70 MB compressed. Consider a separate `computron:slim` image without Node for users who only use built-in integrations (no MCP). Probably not worth the maintenance burden.
- **Non-root rootless Podman mode.** The current setup assumes root inside the container (to `chown` at startup). In rootless Podman, UID 0 is mapped to a subordinate UID on the host; the entrypoint still runs as "root" from the container's POV and `chown` works fine. Verify during testing.
- **Capability hardening** — resolved. `--cap-drop=ALL` + `--security-opt=no-new-privileges` are required (see "Required container security flags" above) and asserted by the supervisor at startup.
