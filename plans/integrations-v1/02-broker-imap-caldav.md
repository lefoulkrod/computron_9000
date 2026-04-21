# 02 — IMAP + CalDAV Brokers

> Two thin Python modules that wrap stdlib + the `caldav` library. Long-lived processes, one per integration, UID 1001. The supervisor spawns and supervises them.

---

## Purpose

Give the app server a small, domain-shaped RPC surface over the IMAP and CalDAV protocols — hiding connection state, TLS, auth, and mailbox/collection selection.

A single Gmail integration spawns **two broker processes** — one IMAP, one CalDAV — with distinct UDS sockets. The supervisor treats them as independent lifecycle units that happen to share a catalog entry. (Alternative: one combined broker. Rejected for v1 because the protocols are stateful in different ways and combining them complicates recovery. Reconsider post-v1.)

Reused verbatim by: Fastmail, iCloud Mail, Outlook.com (consumer), any Custom IMAP/CalDAV host.

---

## Code layout

```
brokers/
├── _common/
│   ├── __init__.py        # facade
│   ├── _rpc.py            # UDS server, length-prefixed JSON, error codes
│   ├── _ready.py          # print("READY", flush=True) helper
│   └── _exit_codes.py     # AUTH_FAIL = 77, etc.
├── imap_broker/
│   ├── __init__.py
│   ├── __main__.py        # entry: env → connect → serve
│   ├── _session.py        # imaplib wrapper, retry/reconnect logic
│   └── _verbs.py          # domain verbs (see below)
└── caldav_broker/
    ├── __init__.py
    ├── __main__.py
    ├── _session.py        # caldav.DAVClient wrapper
    └── _verbs.py
```

Each broker is launched as `python -m brokers.imap_broker` / `python -m brokers.caldav_broker`.

---

## Config at spawn time

The supervisor passes the broker everything it needs via environment variables. Examples:

**IMAP broker:**
```
INTEGRATION_ID=gmail_personal
BROKER_SOCKET=/run/cvault/brokers/gmail_personal.imap.sock
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=larry@gmail.com
IMAP_PASS=abcdefghijklmnop
```

**CalDAV broker:**
```
INTEGRATION_ID=gmail_personal
BROKER_SOCKET=/run/cvault/brokers/gmail_personal.caldav.sock
CALDAV_URL=https://apidata.googleusercontent.com/caldav/v2
CALDAV_USER=larry@gmail.com
CALDAV_PASS=abcdefghijklmnop
```

Nothing secret on argv. After startup the broker drops references to the env vars; `cryptography` isn't doing anything fancy here, just normal Python variable discipline.

---

## Startup sequence

```
1. Read env vars; validate required keys present
2. Create UDS server at $BROKER_SOCKET (chmod 0660, chown broker:computron)
3. Attempt first upstream connection + auth
   a. Success → print "READY\n", enter RPC loop
   b. Auth error (LOGIN failed, 401) → exit 77
   c. Anything else → exit 1 with reason on stderr
```

---

## IMAP broker verbs (`imap_broker/_verbs.py`)

Keep the verb set small. The agent doesn't need full IMAP; it needs email primitives.

| Verb | Args | Returns | IMAP mapping |
|---|---|---|---|
| `list_mailboxes` | `{}` | `[{name, attrs}]` | `LIST "" "*"` |
| `search_messages` | `{mailbox, query, limit?}` | `[uid, …]` | `SELECT` + `SEARCH` |
| `fetch_message` | `{mailbox, uid, parts?}` | `{headers, body_text?, body_html?, attachments_meta}` | `SELECT` + `FETCH` |
| `fetch_headers` | `{mailbox, uids}` | `[{uid, headers}]` | `SELECT` + `FETCH (BODY.PEEK[HEADER])` |
| `flag_message` | `{mailbox, uid, flags, add/remove}` | `{ok}` | `STORE` |
| `move_message` | `{mailbox, uid, dest}` | `{new_uid}` | `MOVE` / `COPY+STORE \Deleted` fallback |

**Out of scope for v1:** creating mailboxes, IMAP IDLE (push), server-side threading, APPEND/send (SMTP is a separate discussion).

Query format: Gmail's X-GM-RAW where available, else IMAP SEARCH syntax. Broker tries `X-GM-RAW` and falls back on error.

---

## CalDAV broker verbs (`caldav_broker/_verbs.py`)

| Verb | Args | Returns | CalDAV mapping |
|---|---|---|---|
| `list_calendars` | `{}` | `[{url, name, color, is_default}]` | principal → calendar-home-set → PROPFIND |
| `list_events` | `{calendar_url, start, end, limit?}` | `[{uid, summary, start, end, location, attendees}]` | REPORT calendar-query |
| `get_event` | `{calendar_url, uid}` | `{raw_ics, parsed}` | GET |
| `create_event` | `{calendar_url, event}` | `{uid, href, etag}` | PUT |
| `update_event` | `{calendar_url, uid, event, etag?}` | `{etag}` | PUT with If-Match |
| `delete_event` | `{calendar_url, uid, etag?}` | `{ok}` | DELETE with If-Match |

Events cross the wire as normalized JSON. The broker owns iCalendar ↔ JSON translation so the app server never sees iCalendar.

---

## RPC protocol (`_common/_rpc.py`)

Shared with all brokers. Length-prefixed JSON frames over UDS.

```
request  : <4-byte BE length><JSON: {"id": n, "verb": "...", "args": {...}}>
response : <4-byte BE length><JSON: {"id": n, "result": ...}>
error    : <4-byte BE length><JSON: {"id": n, "error": {"code": "...", "message": "..."}}>
```

Error codes the supervisor reacts to:

- `"AUTH"` — upstream auth failed mid-session → supervisor flips to `auth_failed`
- `"NETWORK"` — transient; broker retries internally, surfaces after N attempts → `error`
- `"UPSTREAM"` — 5xx or malformed response → reported but broker stays up
- `"BAD_REQUEST"` — verb invoked wrong; app-server bug

---

## Connection lifecycle

Both brokers keep one upstream connection per session. IMAP `SELECT` state is tracked per-request (switch mailbox lazily). CalDAV is mostly stateless per HTTP call but connection pooling (via `requests.Session`) is preserved.

**Reconnect policy:** on connection drop or idle timeout, broker reconnects transparently. If reconnect fails 3x in 30s → exit with the appropriate code (77 if auth error, 1 otherwise). Supervisor sees the exit and transitions to `auth_failed` or triggers the retry backoff.

---

## Dependencies

- **IMAP broker:** stdlib `imaplib` (sync; we wrap in a worker thread), `email` for MIME parsing.
- **CalDAV broker:** `caldav` library (pip), `icalendar` for iCal parsing. Both add to `pyproject.toml`.

Both brokers import the shared `brokers._common` package for RPC, ready-signaling, and exit-code constants.

---

## Implementation milestones

1. `_common/_rpc.py` + unit tests on frame encoding/decoding.
2. `imap_broker` against a real IMAP stub (the stdlib has `imaplib` and `email`; we can stand up a local fake).
3. `caldav_broker` against a fake DAV server (`radicale` in a pytest fixture).
4. Exit-code handling — simulate auth failure, connection loss.
5. End-to-end: supervisor spawns, broker connects to a real Gmail test account (manual smoke test).

---

## Testing notes

- Unit tests use stub sockets + in-process verb dispatch — no real IMAP/CalDAV.
- Keep `imaplib` calls in `_session.py` so the rest of the broker is easy to unit-test.
- Per CLAUDE.md and project memory: **no integration tests** that require external services. Gmail smoke test is a manual step in the PR checklist, not CI.

---

## Component-local open items

- **Attachment handling.** Downloading large attachments over UDS is awkward. v1 returns metadata only; if an attachment is needed, we add a `fetch_attachment` verb that streams bytes (and we revisit the wire protocol for backpressure).
- **Calendar-color handling.** Gmail CalDAV color metadata is non-standard; might need per-provider normalization in `07-catalog.md`.
- **Rate limiting.** Gmail will throttle excessive IMAP searches. Broker should surface 429-equivalents as `NETWORK` with a hint. Implementation deferred.
