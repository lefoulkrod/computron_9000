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

### Ensure `gosu` (or `setpriv`) is installed

The entrypoint drops privilege for each long-running service:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
 && rm -rf /var/lib/apt/lists/*
```

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

### Drop capabilities

```dockerfile
# Container should not need these at runtime
# Add to entrypoint: capsh --drop=... before dropping UID
```

Or rely on Docker's default `--cap-drop=ALL --cap-add=NET_BIND_SERVICE` guidance in the README. Runtime-level concern.

---

## Entrypoint script

New or updated `container/entrypoint.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. First-time volume prep. Runs as root.
VAULT=/var/lib/computron/vault
mkdir -p "$VAULT/creds"
chown -R broker:broker "$VAULT"
chmod 0700 "$VAULT"
chmod 0700 "$VAULT/creds"

# 2. Tmpfs for UDS sockets. Container already has /run writable; ensure cvault/ dir.
RUN=/run/cvault
mkdir -p "$RUN/brokers"
chown broker:broker "$RUN" "$RUN/brokers"
chmod 0750 "$RUN"                # readable by broker; supervisor chmods sockets individually
chmod 0750 "$RUN/brokers"

# 3. Start broker supervisor as UID broker (1001) in the background.
gosu broker python -m broker_supervisor &
SUPERVISOR_PID=$!

# 4. Wait for app.sock to appear so app server doesn't race the supervisor.
for i in {1..50}; do
  [ -S /run/cvault/app.sock ] && break
  sleep 0.1
done
if [ ! -S /run/cvault/app.sock ]; then
  echo "supervisor failed to bind app.sock" >&2
  exit 1
fi

# 5. Start app server as UID computron (1000). Existing behavior.
exec gosu computron python -m main
```

Key properties:

- Entrypoint runs as root, drops per-service after initial setup.
- Supervisor binds `app.sock` before the app server starts → no race.
- Exec'ing the app server means PID 1 is the app server. If it dies, container dies (good). Supervisor is a child; if supervisor crashes, entrypoint doesn't currently notice — see open items.

### Alternate: s6-overlay / tini

For proper multi-service supervision (restart the supervisor if it crashes without taking down the whole container), we'd adopt `s6-overlay` or similar. Probably overkill for v1 — if the supervisor crashes we want to notice anyway, and container restart is a reasonable recovery. But worth flagging.

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

Supervisor + brokers log to stderr → captured by the container runtime. Prefix with the integration ID where applicable so `docker logs computron` is navigable:

```
[supervisor] starting, loaded 2 integrations
[broker:gmail_personal.imap] connecting to imap.gmail.com:993
[broker:gmail_personal.imap] READY
[broker:github_main.mcp] spawned uvx github-mcp (pid=2341)
[broker:github_main.mcp] tools/list returned 12 tools
[broker:github_main.mcp] READY
```

Keep logs boring. No structured logging in v1 (no `structlog`) — plain stdlib `logging` with the per-component formatter.

---

## Implementation milestones

1. Dockerfile: add `broker` user, install `gosu` and Node.js.
2. `entrypoint.sh`: vault setup + dual-process launch.
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

- **Supervisor crash recovery.** Current entrypoint doesn't restart the supervisor if it dies. Short-term: container restarts (Docker policy). Long-term: s6-overlay or a tiny supervisor-of-supervisors in the entrypoint.
- **Image size.** Adding Node.js is ~70 MB compressed. Consider a separate `computron:slim` image without Node for users who only use built-in integrations (no MCP). Probably not worth the maintenance burden.
- **Non-root rootless Podman mode.** The current setup assumes root inside the container (to `chown` at startup). In rootless Podman, UID 0 is mapped to a subordinate UID on the host; the entrypoint still runs as "root" from the container's POV and `chown` works fine. Verify during testing.
- **Capability hardening.** Drop all caps except what's truly needed. Neither supervisor nor brokers need `CAP_NET_BIND_SERVICE` (using high ports), `CAP_SETUID`, or anything else. Default `--cap-drop=ALL` should work. Test.
