# Integrations

## What an integration is

An *integration* is a credentialed connection to an external service the agent can read from and (optionally) write to. v1 supports two:

| Provider | Capabilities | Auth |
|---|---|---|
| iCloud | Email (IMAP + SMTP) + Calendar (CalDAV) | App-specific password |
| Gmail | Email (IMAP + SMTP) | App-specific password |

Each integration becomes one or more agent tools — `list_email_messages`, `move_email`, `send_email`, `list_calendars`, `list_events`, etc. The tools take an explicit `integration_id` argument (e.g. `"icloud_personal"` or `"gmail_work"`), so the agent picks which inbox to operate on per call.

---

## Process model

Three OS users at runtime:

| User | UID | Owns |
|---|---|---|
| `computron` | 1000 | The aiohttp app, the agent, the browser tools, all user-uploaded files |
| `broker` | 1001 | The supervisor, every broker subprocess, the encrypted vault, runtime sockets |
| `root` | 0 | Container init only — drops to the two above via `gosu` in `entrypoint.sh` |

`computron` is in the `broker` group, so it can `connect()` to the broker sockets at `/run/cvault/`. It can't read the vault directory (`/var/lib/computron/vault`, mode `0700` `broker:broker`).

The supervisor runs as a long-lived process that owns:

- The encrypted credential store under `/var/lib/computron/vault/`.
- One **broker subprocess per integration**. Brokers are independent processes that hold the decrypted credential in their own memory and connect directly to the upstream provider (Gmail's IMAP, iCloud's CalDAV, etc.).
- The `app.sock` UDS at `/run/cvault/app.sock`. The aiohttp app talks to this when the user adds, edits, or removes an integration.

```
┌─────────────────────────────────────────────────────────────┐
│ container                                                   │
│                                                             │
│  computron (UID 1000)              broker (UID 1001)        │
│  ────────────────────              ──────────────────       │
│  aiohttp app                       supervisor               │
│   │ (HTTP routes,                   │ (vault, spawn,        │
│   │  agent runtime)                 │  RPC dispatch)        │
│   │                                 ├── email_broker[icloud]│
│   ├── /api/integrations ───────────►│      │  imap+smtp     │
│   │   (PATCH/DELETE/POST)           │      │  TLS to icloud │
│   │     via app.sock                │      ↓                │
│   │                                 │   imap.mail.me.com    │
│   │                                 │                       │
│   ├── tool_call ───────────────────►├── email_broker[gmail] │
│   │   via per-broker socket         │      │  imap+smtp     │
│   │   /run/cvault/<id>.sock         │      ↓                │
│   │                                 │   imap.gmail.com      │
│                                                             │
│  /var/lib/computron/vault/ (mode 0700 broker:broker)        │
│  /run/cvault/                       (mode 0750 broker:broker)
└─────────────────────────────────────────────────────────────┘
```

The agent never has read access to a credential — its UID can't open the vault, and brokers wipe the credential out of `os.environ` after reading it into the IMAP/SMTP/CalDAV client objects.

---

## Permissions model

Every integration has a `write_allowed` flag. Default: **off**. Writes mean anything that mutates upstream state — `send_email`, `move_email`, future `flag_email`, future calendar `create_event` / `delete_event`.

**Two layers** enforce this:

1. **Broker-side gate (the real security boundary).** The supervisor passes `WRITE_ALLOWED=true|false` in the broker's env at spawn. The broker refuses write-tagged verbs locally with `WRITE_DENIED` when the flag is false — the request never reaches upstream. An agent that bypasses `broker_client` and connects directly to the broker's UDS still gets refused.

2. **App-server-side gate (UX).** Write tools are hidden from the agent's tool registry when `write_allowed=false`; `broker_client.call()` short-circuits denied writes with `IntegrationWriteDenied` before a wire round-trip.

Toggling `write_allowed` requires respawning the broker (the env-var is read at startup). The supervisor handles this transparently: the integration goes `running → respawning → running` for ~1–3 seconds. The user's credential is reused; no reconnect prompt.

---

## How credentials are stored

Per-integration files in the vault directory:

```
/var/lib/computron/vault/
├── master.key                        # 32-byte AES-256 key, mode 0600
├── icloud_personal.meta              # plaintext JSON: id, slug, label, write_allowed, timestamps
├── icloud_personal.enc               # AES-256-GCM(plaintext_blob, key=master, aad=integration_id)
├── gmail_work.meta
└── gmail_work.enc
```

The plaintext blob is a JSON object the auth plugin defines — for `app_password`, it's `{"email": "...", "password": "..."}`. The supervisor decrypts it at broker spawn time and passes the relevant fields as env vars (`IMAP_USER`, `IMAP_PASS`, etc.); the broker reads them into client objects on its first IMAP/CalDAV connect, then `os.environ.pop()`s the password.

**Encryption details:**

- AES-256-GCM. Random 12-byte nonce per blob, prepended to the ciphertext.
- AAD = the integration ID, so re-using a stale blob under a different name would fail to decrypt.
- A version byte at the start (`0x01`) reserves room for future format changes.
- The master key is a 32-byte CSPRNG output, written once to `master.key` on first supervisor boot. **It does not rotate** in v1 — see [follow-ups](../plans/integrations-followups.md) for the planned rotation command.

The master key is on local disk at mode `0600 broker:broker`. If an attacker can read that file *and* the `.enc` blobs, they have your credentials. Treat the `/var/lib/computron/vault/` volume the same way you'd treat a password-manager backup.

---

## State machine

Each integration has a state visible in the UI. Transitions are driven by broker process events (the supervisor watches `proc.wait()` exit codes) and user actions.

| State | Meaning | UI affordance |
|---|---|---|
| `pending` | Just added; broker is starting; verify in flight | Spinner |
| `running` | Broker up, upstream auth ok | Green dot, label `connected` |
| `auth_failed` | Broker exited with code 77 — upstream rejected the credential | Red dot, "Credentials were rejected. Delete and re-add to refresh." |
| `broken` | Broker exited non-77 three times in a row before READY | Red dot, "Couldn't reach this integration. Delete and re-add." |

Auto-restart policy:

- **`auth_failed`** is sticky. The supervisor stops respawning. Recovery is delete-and-re-add (you generate a fresh app password and reconnect).
- **Generic crashes** (anything except exit 77) trigger exponential backoff respawn: 1s → 2s → 4s → 8s → 16s, capped at 30s. After three consecutive failures the integration flips to `broken` and respawn stops.
- **Idle drops** (the IMAP/CalDAV connection getting closed by the server after ~10–30 minutes of inactivity) are handled inside the broker — the next verb call catches `imaplib.IMAP4.abort` / `requests.exceptions.ConnectionError`, re-LOGINs, and retries once. The state stays `running` throughout.

---

## Adding, editing, deleting

All UI actions live under **Settings → Integrations** in the app.

**Add** opens a wizard: pick provider → see the explainer + deep-link to the provider's app-passwords page → paste email + password → submit. The supervisor encrypts the blob to `<id>.enc.tmp`, spawns the broker, and renames to `<id>.enc` only after the broker prints `READY\n`. If the credential is bad, the temp file is deleted and the UI gets back an `AUTH` Callout ("iCloud rejected the password — generate a fresh one and paste it again").

**Edit** uses a master-detail layout: list on the left, detail pane on the right. You can change the **label** (cosmetic — meta-only update, no broker respawn) and the **Allow writes** toggle (env change → broker respawn). Save is disabled until something differs from the server state.

**Delete** is one-click + browser confirm. Removes both `.meta` and `.enc`, SIGTERMs the broker, and deletes the per-broker socket file.

The wizard does **not** support renaming the integration ID after the fact — only the label.

---

## Files & locations

| Path | Owner | Mode | Purpose |
|---|---|---|---|
| `/var/lib/computron/vault/` | `broker:broker` | `0700` | Encrypted credential store + master key |
| `/var/lib/computron/vault/master.key` | `broker:broker` | `0600` | AES-256 master key |
| `/var/lib/computron/vault/<id>.meta` | `broker:broker` | `0640` | Plaintext metadata (label, write_allowed, slug) |
| `/var/lib/computron/vault/<id>.enc` | `broker:broker` | `0640` | Encrypted credential blob |
| `/run/cvault/` | `broker:broker` | `0750` | tmpfs — runtime sockets |
| `/run/cvault/app.sock` | `broker:broker` | `0660` | Supervisor RPC; computron group can connect |
| `/run/cvault/<id>.sock` | `broker:broker` | `0660` | Per-broker verb dispatch socket |
| `/run/cvault/attachments/` | `broker:broker` | `2770` | Side channel for fetched email attachments |

The `attachments/` directory uses setgid + sticky bits so both `broker` (writer) and `computron` (reader, downloads dir owner) can play nice without either being able to delete the other's files.

---

## Troubleshooting

**Integration shows `auth failed` shortly after add.**
The credential was wrong, expired, or revoked. Generate a fresh app password (the wizard includes a deep-link to your provider's app-passwords page) and re-add the integration. Existing app passwords are not editable in place — delete and re-add.

**Integration shows `not running` (`broken` state).**
The broker crashed three times in a row before completing its initial handshake. Check `docker logs <container>` for `[email_broker[<id>]]` entries — common causes are network egress blocked (firewall, DNS), the upstream provider being down, or a TLS handshake failure. Delete and re-add once the underlying issue is resolved.

**Integrations tab shows "Integrations unavailable" with a Try again button.**
The aiohttp app can't reach the supervisor. The supervisor process probably crashed or isn't running. In dev mode (`DEV_MODE=true`), the entrypoint respawns it automatically; in prod mode the container will exit and Docker's restart policy takes over. If it persists, check `docker logs` for `[supervisor]` errors.

**The agent says it can't list emails but the UI shows `connected`.**
The broker reconnects automatically when the upstream server drops an idle connection. Check the container logs for `IMAP connection stale (...); reconnecting and retrying once` — if you see that line followed by a successful `IMAP LOGIN ok`, the broker recovered and the next agent call should work. If the reconnect itself fails, treat it as a real network or upstream issue (provider down, DNS / egress blocked).

---

## Security model

**What it defends against:**

- **Agent prompt-injection or runaway tool calls reading credentials.** The agent (UID 1000) cannot open the vault directory (mode `0700`, owned by UID 1001). Even an agent with `bash-run` cannot read `master.key` or any `.enc` blob. The credential only exists in plaintext in the broker process's memory.
- **An agent bypassing `broker_client` to connect directly to a broker's UDS.** The broker enforces `WRITE_ALLOWED` at verb dispatch — the request is rejected before reaching upstream regardless of which client called it.
- **Credentials leaking into argv.** Credentials are passed via env, never argv. The broker `os.environ.pop("EMAIL_PASS", None)`s the password into client-object state immediately after reading it, so a `cat /proc/<pid>/environ` from another UID won't find it.
- **Default-private new files.** The supervisor and brokers install `umask 0077` at startup (per `integrations/_perms.py`), so any file or directory they create without an explicit mode lands at owner-only by default. Sockets that genuinely need group access get an explicit `chmod 0660` after bind.
- **Credentials leaking via core dumps.** The supervisor and brokers call `setrlimit(RLIMIT_CORE, (0, 0))` at startup, so a crash can't write the process's memory to a core file where another UID might read it.
- **A malicious app server respawn somehow setting `WRITE_ALLOWED=true`.** The supervisor is the only thing that spawns brokers; the app server has no broker-spawn surface.

**What it does NOT defend against (explicit non-goals for v1):**

- **Container breakout.** If an attacker escapes the container as root or breaks the UID 1000/1001 boundary, all bets are off.
- **Backup theft.** The state volume contains both the master key and the encrypted blobs. Treat backups like a password-manager export.
- **`ptrace`-based memory inspection.** v1 doesn't assert `kernel.yama.ptrace_scope >= 1` at startup or refuse to run with `CAP_SYS_PTRACE`. The kernel default already blocks the realistic cross-UID attack (agent UID can't ptrace broker UID without `CAP_SYS_PTRACE`), but if the container is launched with that capability granted, an in-container same-UID-as-broker attacker could attach a debugger and read the credential. Asserting these flags at startup is a follow-up item.
- **An MCP server (when MCP lands) abusing creds it was given.** Mitigation is "user consented by installing it." Per-integration egress allowlists are a future hardening item.
- **Disk-level forensic recovery.** We don't shred old `.enc.tmp` files, just `unlink()` them.

---

## Code map

| Component | Path |
|---|---|
| Supervisor (vault, lifecycle, RPC) | `integrations/supervisor/` |
| Email broker (IMAP + SMTP + CalDAV) | `integrations/brokers/email_broker/` |
| Wire framing + ready signal + exit codes | `integrations/_rpc.py`, `integrations/brokers/_common/` |
| Provider catalog | `integrations/supervisor/_catalog.py` (currently inline; moves to `config/integrations_catalog/*.json` per [follow-ups](../plans/integrations-followups.md)) |
| App-server HTTP routes | `server/_integrations_routes.py` |
| Agent-side broker client | `integrations/broker_client/` |
| Agent tool wrappers | `tools/integrations/` |
| React UI | `server/ui/src/components/integrations/` |

Tests live in `tests/integrations/`, `tests/tools/integrations/`, and `e2e/settings/test_integrations.py`.

---

See [`plans/integrations-followups.md`](../plans/integrations-followups.md) for what's next.
