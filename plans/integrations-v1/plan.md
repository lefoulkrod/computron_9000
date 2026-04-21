# Integrations v1 — Broker Supervisor + MCP Plugins

> **Status:** Draft
> **Branch:** `plan/integrations-v1`
> **Last updated:** 2026-04-20

---

## Goals

1. Connect **consumer Gmail + Google Calendar** with setup a non-technical user can finish in under three minutes — no developer console, no OAuth consent screens.
2. Keep the **"credentials never accessible to the `computron` app-server user"** property so the agent cannot exfiltrate secrets.
3. Make **first-party integrations** (email, calendar, filesystem) and **MCP-server plugins** share one plumbing model, so adding new data sources is a plugin concern, not a core-engine concern.
4. Fit the existing container runtime (Ubuntu 22.04, `computron` UID 1000, Podman) with minimal new surface area.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Computron Container                                                    │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  broker-supervisor (broker, UID 1001)                         │      │
│  │  • Reads .master-key, decrypts creds/<id>.enc on demand       │      │
│  │  • Spawns one broker per enabled integration (plain fork+exec)│      │
│  │  • Injects creds via env vars at spawn, never command-line    │      │
│  │  • Monitors health, restarts on crash                         │      │
│  │  • Serves /run/cvault/app.sock (app-server control RPC)       │      │
│  └──────────────────────────────┬───────────────────────────────┘      │
│                                 │                                       │
│       ┌─────────────────────────┼─────────────────────────┐            │
│       │                         │                         │            │
│  ┌────▼────────┐       ┌────────▼────────┐       ┌────────▼────────┐  │
│  │ imap-broker │       │ caldav-broker   │       │ github-mcp      │  │
│  │ (broker)    │       │ (broker)        │       │ (broker)        │  │
│  │ stdlib      │       │ stdlib requests │       │ stdio MCP       │  │
│  │ imaplib     │       │ caldav          │       │ subprocess      │  │
│  └─────┬───────┘       └────────┬────────┘       └────────┬────────┘  │
│        │                        │                          │           │
│        └────── plain TLS to the internet (no proxy) ───────┘           │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │  app-server (computron, UID 1000)                             │     │
│  │  • Tool handlers call broker_client over brokers/<id>.sock    │     │
│  │  • UI talks to supervisor via /api/integrations/*             │     │
│  │  • Never sees decrypted creds                                 │     │
│  └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│  /var/lib/computron/vault/        ← subdir of computron_state volume   │
│  ├── .master-key                  (broker:broker 0600)                 │
│  └── creds/                                                             │
│      ├── gmail_personal.enc       (broker:broker 0600, AES-256-GCM)    │
│      └── github_main.enc          (broker:broker 0600, AES-256-GCM)    │
│                                                                         │
│  /run/cvault/                     ← tmpfs                              │
│  ├── app.sock                     (broker:computron 0660)              │
│  └── brokers/<id>.sock            (broker:computron 0660)              │
└─────────────────────────────────────────────────────────────────────────┘
```

### Two UIDs at runtime

| UID | User | Owns |
|---|---|---|
| 1001 | `broker` | Master key, ciphertext, supervisor process, all brokers + MCP subprocesses. Holds cleartext creds in memory. Talks to the internet. |
| 1000 | `computron` | App server, agent, tool handlers, UI. No cred access. Can reach the internet as before. |

**Root is used only briefly at container boot** — the entrypoint runs as root long enough to `chown broker:broker /var/lib/computron/vault/`, assert directory perms are `0700`, then `gosu` drops each long-running service to its own UID. No process keeps root privilege past startup.

The non-exfiltration property comes from the UID split: `computron` cannot read broker memory, `/proc/<broker-pid>/environ`, or any file in `vault/`.

---

## Credential storage

Deliberately minimal. One master key, one AEAD, per-integration ciphertext files.

### Scheme

- **Master key:** 32 random bytes generated on first container boot. Stored at `/var/lib/computron/vault/.master-key`, `0600 broker:broker`.
- **Cipher:** AES-256-GCM via `cryptography.hazmat.primitives.ciphers.aead.AESGCM`. Nonce stored with ciphertext. Integration ID used as AAD.
- **Per-integration files:** `/var/lib/computron/vault/creds/<id>.enc`, `0600 broker:broker`. Adding or removing one integration never rewrites another.
- **No HKDF, no KEK/DEK split, no tmpfs copy of the key, no rotation command.** If rotation is needed later, it's additive — the on-disk format reserves a 1-byte version header so future schemes can coexist.

### Storage location

Carve a subdirectory out of the existing `computron_state` volume rather than introduce a new volume:

```
/var/lib/computron/                  (computron:computron 0755)
├── conversations/                   (computron)
├── memory/                          (computron)
├── profiles/                        (computron)
├── goals/                           (computron)
└── vault/                           (broker:broker 0700)   ← agent gets EACCES
    ├── .master-key
    └── creds/
        ├── gmail_personal.enc
        └── github_main.enc
```

The entrypoint (root, at boot only) ensures `vault/` ownership and mode. **Startup assertion:** if `vault/` is not owned by `broker:broker` at mode `0700`, the supervisor refuses to start. This catches future image regressions before they silently expose creds.

### What encryption buys in this scheme

- Defense against file-permission regressions (0600 → 0644 by accident).
- Defense against log/support-bundle leaks (nothing on disk is ever plaintext).
- Defense against core dumps — additionally, broker processes run with `ulimit -c 0`.

### What it doesn't buy

Backup safety. The master key and ciphertext live in the same volume; anyone with `docker volume export computron_state` gets both. This is **explicit non-goal** for v1 — see the Settings UI copy in the UX walk-through. A future Go CLI wrapper is the likely home for a smarter key-storage scheme.

### Stored blob shape

Decrypted payload (one file per integration):

```json
{
  "version": 1,
  "id": "gmail_personal",
  "kind": "imap_caldav",
  "label": "Gmail — personal",
  "email": "larry@gmail.com",
  "auth": { "type": "app_password", "value": "abcd efgh ijkl mnop" },
  "hosts": { "imap": "imap.gmail.com:993", "caldav": "apidata.googleusercontent.com" },
  "added_at": "2026-04-20T12:00:00Z"
}
```

For MCP subprocesses the shape adds a `server` block alongside `auth`:

```json
{
  "version": 1,
  "id": "github_main",
  "kind": "mcp_subprocess",
  "label": "GitHub",
  "server": {
    "command": "uvx",
    "args": ["github-mcp"],
    "transport": "stdio",
    "env_from_vault": { "GITHUB_PERSONAL_ACCESS_TOKEN": "token" }
  },
  "auth": { "type": "bundle", "fields": { "token": "ghp_xxx" } },
  "added_at": "2026-04-20T12:05:00Z"
}
```

---

## Auth plugin types

Four shapes cover essentially every integration we care about. Each is a module in `broker_supervisor/auth/` that implements `BootstrapFlow`, `Verify`, and `EnvInjection`.

### 1. `app_password`
- **Flow:** deep-link to provider's app-password page → paste → verify.
- **Providers:** consumer Gmail, iCloud Mail/Calendar, Fastmail, consumer Outlook, Yahoo, generic IMAP/CalDAV.
- **Verify:** broker attempts `LOGIN` / `PROPFIND` against the configured host.
- **v1 provider set:** Gmail only. Other IMAP/CalDAV providers land post-v1 via the "Custom IMAP/CalDAV" escape hatch.

### 2. `api_key` / `personal_access_token`
- **Flow:** deep-link to provider's token page → paste → verify.
- **Providers:** GitHub, Notion, Linear, Todoist, Home Assistant long-lived token, OpenAI, Anthropic, arbitrary MCP servers that take a bearer token.
- **Verify:** broker calls the provider's `/user` or equivalent identity endpoint.

### 3. `oauth2_pkce`
- **Flow:** click "Connect" → Computron opens the provider's authorize URL in the user's browser → redirect lands at `http://127.0.0.1:<ephemeral>/callback` → broker exchanges the code for tokens → refresh token encrypted into vault.
- **Providers:** Spotify (public-client PKCE is supported), Google Workspace if/when we tackle it, any modern OAuth2 provider.
- **Not in v1** as a shipped flow, but the vault schema and UI affordances should leave room so we don't refactor later.

### 4. `mcp_subprocess`
- **Flow:** user picks an MCP server from a curated list or pastes a command. Wizard collects the server's required config fields (declared by the server's manifest or a Computron-side metadata file). Fields are stored in the vault and injected at spawn time.
- **Transport:** stdio for v1 (most mature). Streamable HTTP transport later.
- **Verify:** spawn the server, call `tools/list`, confirm ≥1 tool is returned, kill.
- **Security:** the MCP subprocess inherits UID `broker`. No access to `computron`'s filesystem outside shared UDS sockets.

---

## v1 integration slate

Two integrations, each exercising a different auth plugin and integration kind — that gets the whole plumbing validated end-to-end.

| # | Integration | Kind | Auth | Why this one |
|---|---|---|---|---|
| 1 | Gmail (email + calendar) | built-in broker | `app_password` | Primary user goal. Proves the IMAP + CalDAV path and the `app_password` plugin. |
| 2 | GitHub | MCP subprocess | `personal_access_token` | Near-total audience overlap. Official `github-mcp` server, one-step PAT auth. Proves the MCP-subprocess path and the `api_key` plugin. |

**Deliberately deferred:** Fastmail and other IMAP/CalDAV providers (Gmail proves the path; add via "Custom IMAP/CalDAV" until we curate more), Home Assistant, Notion, Linear, Spotify (needs OAuth plumbing), Outlook.com (Microsoft's consumer stance is shaky right now), Google Workspace (needs verified OAuth app — revisit when user base justifies it).

---

## UX walk-through

### First-run onboarding

1. Container comes up empty. Settings → Integrations tab is highlighted with a "Connect a service to get started" prompt.
2. User clicks **Add Integration**. Modal opens with a picker grouped by kind: **Email & Calendar**, **Dev Tools**, **Smart Home**, **Productivity**, **Custom MCP Server**, **Custom IMAP/CalDAV**.
3. User picks Gmail. Wizard step 1 explains "We need an app password. Click the button below to open Google's page in a new tab, then paste the password here. This stays on your machine, encrypted."
4. Deep-link button: `https://myaccount.google.com/apppasswords`. Below it, an input for email and one for the 16-char app password. A "Test connection" button runs verify before save.
5. Success state shows encrypted-storage summary, and the integration appears in the list with a green status dot.

### Adding an MCP server

1. **Add Integration → Custom MCP Server.**
2. Wizard: pick from the curated list (GitHub in v1) *or* paste a stdio command.
3. For each declared field (URL, token, …), show an input and a deep-link to the provider's docs where applicable.
4. Verify spawns the server, calls `tools/list`, reports the tool count.
5. On success: integration stored, broker supervisor starts the server, tools become available to the agent.

### Ongoing

- List shows status dot per integration (connected / disconnected / pending).
- Row actions: **Verify** (re-run the handshake), **Reconnect** (collect fresh creds), **Remove** (delete from vault).
- Vault status strip at the bottom: `Vault: ready • AES-256-GCM • 3 integrations`.

---

## API surface

All app-server-facing endpoints are proxied onto the vault via `/run/cvault/app.sock`.

| Method | Path | Handler | Notes |
|---|---|---|---|
| `GET` | `/api/integrations` | list | Returns integrations with status, never cred values. |
| `POST` | `/api/integrations` | add | Validates + encrypts + starts broker. |
| `DELETE` | `/api/integrations/:id` | remove | Stops broker, removes from vault. |
| `POST` | `/api/integrations/:id/verify` | verify | Re-runs health check. |
| `PATCH` | `/api/integrations/:id` | update | Label-only; cred changes require re-add for audit. |
| `GET` | `/api/integrations/catalog` | catalog | Returns the curated provider list. |

Tool handlers use an **internal** client that does *not* go through `/api/*`:

```python
# tools/email/search.py
from broker_client import get_broker

async def search_email(integration_id: str, query: str) -> list[EmailHeader]:
    broker = await get_broker(integration_id)  # resolves to broker UDS
    return await broker.call("search", query=query)
```

The broker client resolves integration IDs through the supervisor, which owns the id→socket map. The app server never sees the upstream host, port, or token.

---

## Security properties

| Asset | Where it lives | Who can read it |
|---|---|---|
| Master key | `/var/lib/computron/vault/.master-key` | `broker` only (0600) |
| Credential ciphertext | `/var/lib/computron/vault/creds/<id>.enc` | `broker` only (0600), AES-256-GCM |
| Decrypted creds (transient) | supervisor memory, only during spawn | `broker` UID only |
| Active integration creds | broker process memory + env | `broker` UID only; `/proc/<pid>/environ` is 0400 owner |
| Non-secret integration metadata | app server state (labels, statuses, IDs) | world-readable within container |

### Threat matrix

| Threat | Mitigation |
|---|---|
| Agent: `cat /var/lib/computron/vault/creds/*.enc` | EACCES; 0600 broker |
| Agent: `cat /var/lib/computron/vault/.master-key` | EACCES; 0600 broker |
| Agent: `ls /var/lib/computron/vault/` | EACCES; parent dir is 0700 broker |
| Agent: `cat /proc/<supervisor-pid>/environ` | EACCES; different UID |
| Agent: `cat /proc/<broker-pid>/environ` | EACCES; different UID |
| Agent: `ptrace` or `/proc/<pid>/mem` on a broker | EACCES; different UID, no `CAP_SYS_PTRACE` |
| Agent spawns its own broker with a tampered command | Supervisor is the only spawner; app server has no exec path to `broker` UID |
| Broker crash core dump leaks creds | Broker processes run with `ulimit -c 0` |
| MCP server exfiltrates creds to its author's server | **Accepted risk.** User consented by installing. Mitigation: per-integration iptables egress allowlist (P2). |
| Host access to the Docker volume | Out of scope. Same as every local-first design. |
| `docker volume export computron_state` | **Leaks creds.** Key and ciphertext in the same volume. Explicit v1 non-goal — revisit via Go CLI. |
| Future image regression ships `vault/` as world-readable | Startup assertion aborts boot if ownership/mode drifts |

### What we intentionally do *not* defend against

- Compromise of the `broker` UID via an RCE in a broker process → active creds exposed.
- Supply-chain compromise of an MCP server the user installed.
- Anyone with `sudo` on the host.
- Backup theft of the `computron_state` volume.

---

## Implementation phases

| Phase | Deliverable | Priority |
|---|---|---|
| 1 | Broker supervisor — AES-256-GCM crypto, master-key lifecycle, spawn/monitor/restart, `app.sock` RPC | P0 |
| 2 | IMAP broker + CalDAV broker (built-in modules) | P0 |
| 3 | `app_password` auth plugin + verify | P0 |
| 4 | `mcp_subprocess` auth plugin + stdio MCP host | P0 |
| 5 | Integrations API routes on the app server | P0 |
| 6 | React Integrations tab — list + Add flow + verify | P0 |
| 7 | Gmail + GitHub provider entries in the catalog | P0 |
| 8 | Container entrypoint changes — add `broker` user, chown `vault/`, start supervisor | P0 |
| 9 | `api_key` auth plugin + verify (direct first-party API calls) | P1 |
| 10 | Custom IMAP/CalDAV escape hatch | P1 |
| 11 | Custom MCP command escape hatch | P1 |
| 12 | Additional curated catalog entries (Fastmail, Home Assistant, Notion, Linear, …) | P1 |
| 13 | `oauth2_pkce` auth plugin | P2 |
| 14 | Per-integration iptables egress allowlist | P2 |
| 15 | Key rotation command | P2 |
| 16 | Streamable HTTP MCP transport | P2 |
| 17 | Smarter key storage (Go CLI-driven) | P2 |

**P0 = v1 release.** Ships Gmail + GitHub working end-to-end with the UID-split security model.

---

## Resolved design decisions

### Architecture

- **No separate vault daemon.** Merged into the broker supervisor. One long-running process owns crypto and supervision. Root only used at entrypoint-time to set `vault/` ownership, then drops out via `gosu`.
- **One broker process per integration** (not per kind). Long-lived, UID 1001. Holds creds in env + memory; restarted by supervisor on crash.
- **Three broker implementations only.** `imap_broker`, `caldav_broker`, `mcp_broker`. Adding a provider = catalog entry + auth plugin, **not new broker code**.

### Supervisor ↔ broker interface

- **No universal RPC contract.** Brokers expose ONLY domain verbs (`search_messages`, `list_events`, `tools/call`, …). Lifecycle is managed via Unix process primitives — `fork`/`exec`, `SIGTERM`, `SIGKILL`, `waitpid`, stdout-read-until-`READY\n`.
- **Readiness signal.** Broker prints `READY\n` to stdout after successful first upstream auth.
- **Exit codes.** `0` = clean shutdown. `77` = auth failure (supervisor flips state to `auth_failed`). Any other nonzero = generic error.
- **Verify = first spawn.** There's no separate verify path. Adding an integration means writing `.enc.tmp`, spawning the broker, and renaming `.tmp` → `.enc` on `READY`.

### Integration state machine

| State | Meaning | UI |
|---|---|---|
| `pending` | just added, or verify in progress | grey + spinner |
| `active` | healthy | green |
| `auth_failed` | creds rejected; requires Reconnect | red |
| `error` | broker crash / network / upstream down; auto-retry with backoff | amber |
| `disabled` | user toggled off; broker not running | grey |

Transitions fired by: **supervisor** (from process events), **broker** (via RPC error codes + exit codes), **user** (Retry/Reconnect/Toggle/Remove).
Auto-retry: exponential backoff (1s → 5s → 30s → 5m) for `error`; never for `auth_failed`; stop after ~30 min and wait for manual Retry.

### Tool ↔ integration binding

- **Explicit `integration_id` parameter** on every tool. `search_email(integration_id, query)`, `list_events(integration_id, range)`, etc.
- **Dynamic tool descriptions.** The tool's description is regenerated whenever integrations change; the list of available IDs appears in-line so the agent can pick based on user intent.
- No implicit auto-routing, no per-integration tool registration.

### Integration ID naming

- Format: `<provider_slug>_<user_suffix>`, `[a-z0-9_-]+`, max 64 chars.
- `provider_slug` comes from the catalog entry (non-editable). `user_suffix` is wizard-edited, defaulting to sanitized first word of the label.
- Collision: auto-append `_2`, `_3`, …, surfaced to user before Save.
- **IDs are not editable after creation.** Labels are.

### Auth bootstrap

- **Auth plugins are schemas, not executable code.** Each plugin module declares `FIELDS` (list of form fields) and `ENV_INJECTION` (map from field names to broker env-var names).
- **Split work:**
  - App server: serves catalog + plugin `FIELDS` to UI; validates form shape; POSTs normalized blob over `app.sock`.
  - Supervisor: encrypts blob to `<id>.enc.tmp`, spawns broker with env, listens for `READY\n`, renames to `.enc` on success / deletes on failure.
  - Broker: does the actual upstream connect — this **is** the verify step.

### Other

- **MCP catalog ships with the app**, one JSON file per entry under `config/integrations_catalog/`. No registry fetch in v1.
- **Multi-account per provider** supported via distinct IDs (`gmail_personal`, `gmail_work`).
- **Disconnected integration = tool stays registered, calls error.** Agent's tool surface stays stable; error message is informative.

---

## Sub-component plans

This plan is decomposed into one file per P0 deliverable. See:

- `01-supervisor.md` — crypto, master key, spawn, lifecycle, `app.sock` RPC
- `02-broker-imap-caldav.md` — built-in IMAP + CalDAV brokers
- `03-broker-mcp.md` — MCP stdio subprocess host
- `04-auth-plugins.md` — `FIELDS` + `ENV_INJECTION` contract; v1 plugins
- `05-api-and-client.md` — `/api/integrations/*` routes + `broker_client` for tool handlers
- `06-ui.md` — React Integrations tab
- `07-catalog.md` — catalog JSON schema + v1 entries
- `08-container.md` — Dockerfile, entrypoint, runtime layout

---

## Out of scope for v1

- SMTP / sending email. Read-only for now.
- OAuth-based Gmail or Workspace. Revisit when user base justifies Google verification spend.
- MCP servers over streamable HTTP.
- Hosted-relay MCPs (Nylas, Composio, Zapier MCP). Shipping them would break the "creds stay local" property; explicit non-goal.
- Plaid / bank connections. Compliance and fraud surface too high for a hobby/prosumer tool.
- WhatsApp, iMessage. ToS hazard.
