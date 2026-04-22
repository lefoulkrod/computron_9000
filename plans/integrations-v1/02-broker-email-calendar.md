# 02 — Email + Calendar Brokers

> Two capability-oriented brokers: the **email broker** speaks IMAP (read) and SMTP (send) in one process, the **calendar broker** speaks CalDAV. Long-lived processes, one per integration, UID 1001. The supervisor spawns and supervises them.

---

## Purpose

Give the app server a small, domain-shaped RPC surface over whatever protocol(s) a capability requires — hiding connection state, TLS, auth, mailbox/collection selection, and the fact that "email" on the wire is actually two separate protocols (IMAP + SMTP).

A single Gmail integration spawns **two broker processes** — one for email, one for calendar — with distinct UDS sockets. The supervisor treats them as independent lifecycle units that happen to share a catalog entry.

### Why capability-oriented brokers, not protocol-oriented

Earlier drafts had `imap_broker` and `caldav_broker` as separate units (one per protocol). Revised after recognizing that:

- **Email is a single user-facing capability** that just happens to use IMAP for read and SMTP for send. Splitting them means two processes holding the same credential for no isolation gain (both need to die together if the password changes; SMTP is stateless so there's no session to protect).
- **Consumer email providers always offer both** (see plan.md "v1 integration slate") — IMAP alone isn't useful because you can't reply; SMTP alone isn't useful because you can't see what you're replying to.
- **The agent sees capability-shaped tools** (`search_email`, `send_message`) — matching the broker surface to that shape keeps the code map easy to follow.

MCP stays protocol-oriented (see `03-broker-mcp.md`) because MCP *is* the boundary being exposed — the capability varies per MCP server.

---

## Code layout

```
brokers/
├── _common/
│   ├── __init__.py        # facade
│   ├── _rpc.py            # UDS server, length-prefixed JSON, error codes
│   ├── _ready.py          # print("READY", flush=True) helper
│   └── _exit_codes.py     # AUTH_FAIL = 77, etc.
├── email_broker/
│   ├── __init__.py
│   ├── __main__.py        # entry: env → connect IMAP → serve (SMTP connects per-send)
│   ├── _imap_session.py   # imaplib wrapper, retry/reconnect logic
│   ├── _smtp_session.py   # smtplib wrapper, fresh connection per send
│   └── _verbs.py          # read + send verbs dispatched through both sessions
└── calendar_broker/
    ├── __init__.py
    ├── __main__.py
    ├── _session.py        # caldav.DAVClient wrapper
    └── _verbs.py
```

Each broker is launched as `python -m brokers.email_broker` / `python -m brokers.calendar_broker`.

---

## Config at spawn time

The supervisor passes the broker everything it needs via environment variables.

**Email broker:**
```
INTEGRATION_ID=gmail_personal
BROKER_SOCKET=/run/cvault/brokers/gmail_personal.email.sock
WRITE_ALLOWED=false              # "true" or "false"; broker refuses write verbs locally when false
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
EMAIL_USER=larry@gmail.com
EMAIL_PASS=abcdefghijklmnop      # same app password, used for both IMAP LOGIN and SMTP AUTH
```

**Calendar broker:**
```
INTEGRATION_ID=gmail_personal
BROKER_SOCKET=/run/cvault/brokers/gmail_personal.calendar.sock
WRITE_ALLOWED=false              # "true" or "false"; broker refuses write verbs locally when false
CALDAV_URL=https://apidata.googleusercontent.com/caldav/v2
CALDAV_USER=larry@gmail.com
CALDAV_PASS=abcdefghijklmnop
```

### Secrets via env, not argv

**Why env and not the command line.** On Linux, a process's command-line arguments (`argv`) live at `/proc/<pid>/cmdline`, which is **world-readable** — any process running under any user can `cat` it, and `ps auxe` will show it by default. A process's environment variables live at `/proc/<pid>/environ`, which is **mode `0400`** — readable only by the same UID that owns the process. Because the broker runs as UID `broker` (1001) and the agent runs as UID `computron` (1000), env is an actual isolation boundary (agent can't read broker's env), while argv would be an immediate leak (agent can read anyone's `cmdline`). So credentials are passed via env vars and never appear on the broker's command line.

### Drop references after startup

Once the broker has read what it needs out of `os.environ` (host, user, password, etc.), it `del`s those keys from `os.environ` and drops any local variables that briefly held them. This is **defense-in-depth, not the primary defense** — the UID boundary above is what actually keeps the secret inside the broker process. What dropping references buys us:

- A debugger attaching to the broker (for whatever reason) sees fewer live secret strings.
- An exception traceback that happens to format `os.environ` or a locals dict won't include the password.
- A log line that stringifies a frame or config object can't accidentally include what isn't there anymore.
- A future crash-reporter or telemetry library that captures "context" doesn't pick up the secrets.

Caveat: `del os.environ['EMAIL_PASS']` does **not** change what `/proc/<pid>/environ` reports. Linux's initial-env region is established at `exec()` time and glibc doesn't update it when the process modifies env at runtime. But we don't care about that file anyway — it's mode `0400`, so the agent can't read it. The UID boundary holds; the del is hygiene.

*One subtlety for the email broker:* the SMTP session re-authenticates per send, so the broker must hold `EMAIL_PASS` in a non-env location (a private module variable) after the env is wiped. That variable lives inside the broker process's memory only; it's as exposed as everything else in the process, and inherits the same UID protection.

---

## Startup sequence

**Email broker:**
```
1. Read env vars; validate required keys present
2. Parse WRITE_ALLOWED ("true" → True, anything else → False); stash on self
3. Stash EMAIL_PASS in a private module var; del from os.environ
4. Create UDS server at $BROKER_SOCKET (chmod 0660, chown broker:computron)
5. Attempt first IMAP connection + LOGIN
   a. Success → print "READY\n", enter RPC loop
   b. Auth error (LOGIN failed) → exit 77
   c. Anything else → exit 1 with reason on stderr
(SMTP is not connected at startup — it's connect-per-send. First send verifies the password for SMTP;
 if SMTP auth fails persistently mid-session, treatment matches the IMAP auth failure path.)
```

**Calendar broker:**
```
1. Read env vars; validate required keys present
2. Parse WRITE_ALLOWED; stash on self
3. Create UDS server at $BROKER_SOCKET (chmod 0660, chown broker:computron)
4. Attempt first upstream connection + auth (PROPFIND on principal URL)
   a. Success → print "READY\n", enter RPC loop
   b. Auth error (401) → exit 77
   c. Anything else → exit 1 with reason on stderr
```

---

## Email broker verbs (`email_broker/_verbs.py`)

Keep the verb set small. The agent doesn't need full IMAP/SMTP; it needs email primitives. (A design bias, not a law — see plan.md's "Resolved design decisions" and this file's "Component-local open items" for the list of intentionally omitted verbs.)

| Verb | Type | Args | Returns | Protocol |
|---|---|---|---|---|
| `list_mailboxes` | read | `{}` | `[{name, attrs}]` | IMAP `LIST "" "*"` |
| `search_messages` | read | `{mailbox, query, limit?}` | `[uid, …]` | IMAP `SELECT` + `SEARCH` |
| `fetch_message` | read | `{mailbox, uid, parts?}` | `{headers, body_text?, body_html?, attachments_meta}` | IMAP `SELECT` + `FETCH` |
| `fetch_headers` | read | `{mailbox, uids}` | `[{uid, headers}]` | IMAP `SELECT` + `FETCH (BODY.PEEK[HEADER])` |
| `flag_message` | **write** | `{mailbox, uid, flags, add/remove}` | `{ok}` | IMAP `STORE` |
| `move_message` | **write** | `{mailbox, uid, dest}` | `{new_uid}` | IMAP `MOVE` / `COPY+STORE \Deleted` fallback |
| `send_message` | **write** | `{to, cc?, bcc?, subject, body_text?, body_html?, in_reply_to?, references?, attachments?}` | `{message_id}` | SMTP fresh connection + AUTH + `MAIL FROM` + `RCPT TO` + `DATA` + `QUIT` |

### About the `Type` column

The `Type` column (`read` / `write`) gates whether a call is allowed when the integration is in read-only mode. **Two layers enforce it — the broker is primary.**

**Broker-side (primary, security-load-bearing).** The supervisor passes `WRITE_ALLOWED=true|false` in the broker's env at spawn. The broker has its own `_VERB_TYPE` dict mirroring this column; verb dispatch checks it:

```python
async def _dispatch(self, verb, args):
    if _VERB_TYPE[verb] == "write" and not self._write_allowed:
        return {"error": {"code": "WRITE_DENIED",
                          "message": "writes disabled for this integration"}}
    return await self._handlers[verb](**args)
```

This is what makes the gate real. An agent with `bash-run` that connects directly to the broker's UDS — bypassing `broker_client` and the app server's tool registry entirely — still gets refused by the broker itself.

**App-server-side (belt-and-braces, UX/performance).** `broker_client.call()` short-circuits write verbs before the wire round-trip and the app server hides write tools from the agent's registry when the flag is false. These save a round-trip and give the agent a crisp error message. They are **not load-bearing for security** — if they're absent or wrong, the broker still enforces. Described in `05-api-and-client.md`.

### Type-column drift: three places that must agree

The `Type` column is mirrored in two code locations:

1. This table (canonical, human-readable).
2. `broker_client._verb_types._VERB_TYPES` — the client-side short-circuit's map.
3. The broker's own `_VERB_TYPE` dict (defined in `email_broker/_verbs.py` and `calendar_broker/_verbs.py`) — the broker's dispatch check.

If any of the three drifts:

- **Broker const wrong** → real enforcement wrong (security bug). A `write` verb tagged `read` in the broker gets through even when `WRITE_ALLOWED=false`.
- **Client const wrong (broker const right)** → belt-and-braces misfires, but the broker still blocks the call — no security hole, just a confusing error message or an extra wire round-trip.
- **Table wrong** → doc rot, may cause future contributors to misclassify in code.

**Drift-check test** (per `09-testing.md`): a pure-unit test parses this Markdown table, imports both the broker's `_VERB_TYPE` and the client's `_VERB_TYPES`, and asserts all three agree exactly. Runs in `just test-unit`; CI fails on any divergence.

**Alternative considered, deferred.** The broker could expose a `describe` verb that returns `{verb: type}` at connect time, making itself the single source of truth consumed by `broker_client`. Pros: eliminates the client↔broker drift (not the table↔code drift). Cons: extra round-trip at every resolve; per-broker const still has to be written anyway (that's where the broker's own dispatch reads it). For v1 the three-way drift-check approach is simpler. Revisit if the test ever misses a regression in practice.

### Send-message specifics

- Broker assembles the MIME message in-process (`email.message.EmailMessage`) from the structured args.
- Opens a fresh SMTP connection per send: `SMTP(host, port)` → `starttls()` (port 587) or `SMTP_SSL` (port 465) → `login(user, pass)` → `send_message()` → `quit()`.
- Returns the `Message-ID` the provider assigned (or we generated and the provider accepted).
- **Gmail auto-saves to Sent** when sending through `smtp.gmail.com`. We do not IMAP-APPEND for Gmail; for providers that don't auto-save (post-v1 providers like Fastmail), the broker will APPEND the raw message to the Sent mailbox after the SMTP send. Out of scope for the Gmail-only v1.

**Out of scope for v1:** creating mailboxes, IMAP IDLE (push), server-side threading, draft management (IMAP APPEND to Drafts), per-account signature injection, templated bodies. Each is easy to add later when a user request makes it load-bearing.

Query format: Gmail's X-GM-RAW where available, else IMAP SEARCH syntax. Broker tries `X-GM-RAW` and falls back on error.

---

## Calendar broker verbs (`calendar_broker/_verbs.py`)

| Verb | Type | Args | Returns | CalDAV mapping |
|---|---|---|---|---|
| `list_calendars` | read | `{}` | `[{url, name, color, is_default}]` | principal → calendar-home-set → PROPFIND |
| `list_events` | read | `{calendar_url, start, end, limit?}` | `[{uid, summary, start, end, location, attendees}]` | REPORT calendar-query |
| `get_event` | read | `{calendar_url, uid}` | `{raw_ics, parsed}` | GET |
| `create_event` | **write** | `{calendar_url, event}` | `{uid, href, etag}` | PUT |
| `update_event` | **write** | `{calendar_url, uid, event, etag?}` | `{etag}` | PUT with If-Match |
| `delete_event` | **write** | `{calendar_url, uid, etag?}` | `{ok}` | DELETE with If-Match |

Events cross the wire as normalized JSON. The broker owns iCalendar ↔ JSON translation so the app server never sees iCalendar.

---

## RPC protocol (`_common/_rpc.py`)

Shared with all brokers. Length-prefixed JSON frames over UDS.

```
request  : <4-byte BE length><JSON: {"id": n, "verb": "...", "args": {...}}>
response : <4-byte BE length><JSON: {"id": n, "result": ...}>
error    : <4-byte BE length><JSON: {"id": n, "error": {"code": "...", "message": "..."}}>
```

Error codes the **app server** (`broker_client`) maps into exceptions. The supervisor does not see this traffic — it only observes broker **exit codes**. If an error is persistent enough for the broker to give up, the broker exits, and the supervisor reacts to that (see `01-supervisor.md` "Lifecycle").

| Code | Meaning | Broker-side behavior | `broker_client` exception |
|---|---|---|---|
| `AUTH` | Upstream auth rejected. | Transient (single `LOGIN`/SMTP `AUTH` failure after a reconnect, etc.): respond with error, stay alive. Persistent (3 auth failures in 30 s on either protocol): respond with error, then **exit 77** → supervisor flips state to `auth_failed`. | `IntegrationAuthFailed` |
| `NETWORK` | Transient connectivity issue. | Broker retries internally; surfaces only after N attempts. If retries exhaust repeatedly, broker exits 1 → supervisor flips to `error` with backoff. | `IntegrationNetworkError` |
| `UPSTREAM` | 5xx or malformed response from the server. | Reported per-call; broker stays up. | `IntegrationUpstreamError` |
| `BAD_REQUEST` | Verb invoked with wrong args. App-server bug; never an end-user-visible failure if we're doing our job. | Broker stays up. | `ProgrammingError` |

---

## Connection lifecycle

- **IMAP session.** One long-lived connection per broker. `SELECT` state is tracked per-request (switch mailbox lazily). On drop or idle timeout, the broker reconnects transparently.
- **SMTP session.** Fresh connection per send (connect → AUTH → MAIL/RCPT/DATA → QUIT). Short-lived by design; no pooling. This sidesteps the protocol's session-timeout quirks and matches how mail clients behave.
- **CalDAV session.** Mostly stateless per HTTP call; connection pooling via `requests.Session` is preserved.

**Reconnect policy.** On connection drop or idle timeout, the broker reconnects transparently. If reconnect or auth fails 3 times in 30 s on a given protocol, broker exits with the appropriate code — `77` if auth, `1` otherwise. Supervisor sees the exit and transitions state.

The email broker counts IMAP and SMTP auth failures separately but reports either one's exhaustion the same way; the user's app password is shared, so a persistent auth failure on either protocol is a signal that the password is stale.

---

## Concurrency

The app server can run multiple agents simultaneously, which means a broker can receive overlapping RPC calls from different app-server connections. How each protocol handles that:

- **SMTP.** Every `send_message` opens its own short-lived connection, so N concurrent sends use N independent connections. No contention.
- **CalDAV.** Stateless HTTP per call. `requests.Session` maintains a small connection pool (`pool_maxsize` default is 10). Concurrent calendar calls run in parallel; the broker doesn't need to do anything extra.
- **IMAP.** One long-lived session, inherently stateful. Concurrent reads against different mailboxes would collide — see below.

  **IMAP session state primer.** A single IMAP session can only have one mailbox "selected" at a time. The session is a state machine: `SELECT INBOX` puts the session into INBOX, and every subsequent `SEARCH` / `FETCH` / `STORE` applies to INBOX. If the session later issues `SELECT Sent`, it implicitly closes INBOX and opens Sent; there is no way to "hold" two mailboxes at once. This is a property of the IMAP *session*, not of the server — your phone and this broker can have separate sessions, each selecting different mailboxes, without interfering with each other. The concern is only within our one shared session.

  Why it matters for concurrency: if the broker has one IMAP session and two agents call in simultaneously — agent A running `search_messages(mailbox="INBOX", ...)` while agent B fires `fetch_message(mailbox="Sent", ...)` — B's `SELECT Sent` would yank the selected mailbox out from under A's in-flight `SEARCH`. A gets wrong-mailbox results or a protocol error.

  **v1 mitigation: an `asyncio.Lock` around every IMAP operation inside the broker**, plus a cached "current mailbox" so consecutive operations on the same mailbox skip redundant `SELECT` round-trips. Sketch:

  ```python
  async def search_messages(self, mailbox, query, limit):
      async with self._imap_lock:
          if self._current_mailbox != mailbox:
              await self._imap.select(mailbox)
              self._current_mailbox = mailbox
          return await self._imap.search(query, limit)
  ```

  Effect: IMAP verbs serialize through the single session (one operation at a time holds it); SMTP and CalDAV stay parallel. For a human-driven agent workload, the extra queuing latency (tens of ms, maybe one SELECT round-trip) is imperceptible. IMAP is already the slowest hop, so serialization mostly affects throughput, not user-visible latency.

  Not using a connection pool in v1: extra IMAP sessions mean extra `LOGIN` round-trips + extra file descriptors + duplicate session state to keep consistent, for a workload that is almost certainly not bottlenecked on IMAP concurrency. Revisit post-v1 if real traces show contention.

All three protocols' thread-safety stories are handled inside the broker; the app server can treat the broker's UDS as a normal concurrent server. Request IDs on the wire (`{"id": n, ...}`) let the broker multiplex responses back to whichever in-flight request each one belongs to.

---

## Attachments

Side-channel files on a shared tmpfs. One code path, no inline/over-cap branching.

### Directory

```
/run/cvault/attachments/       (broker:computron 0770, tmpfs)
  <random-32-hex>.bin
  <random-32-hex>.bin
  ...
```

Set up by the entrypoint (see `08-container.md`). The `computron` group membership is what lets the app server read files the broker wrote; reverse direction (broker reads files the app server wrote) uses the same group.

### Fetch: broker → app server

```
verb:   fetch_attachment
args:   {message_uid, attachment_id}
result: {path, mime_type, filename, size}
```

Broker extracts the attachment from the IMAP `FETCH BODY[n]` response, writes the raw bytes to `/run/cvault/attachments/<random>.bin` with mode `0640` (group read), and returns the path. The app server (or tool handler) opens the file, streams the contents to wherever needed, and unlinks when done.

### Send: app server → broker

```
verb:   send_message
args:   {..., attachments: [{path, filename, mime_type}, ...]}
```

The app server writes attachment bytes to `/run/cvault/attachments/<random>.bin` first (mode `0640`, owned `computron:computron` — broker reads via group), passes the paths in the RPC call, then unlinks its files after the send returns. The broker reads each file during MIME assembly; it does not delete the caller's files.

### Cleanup

- **Happy path.** Producer unlinks its own files as soon as the consumer is done. Both sides know when they're done — app server after it has streamed the attachment out of a tool response; broker after `send_message` returns.
- **Idle-GC.** The supervisor sweeps `/run/cvault/attachments/` every 60 s and unlinks any file older than 5 minutes. Catches leaks from crashes mid-handoff. (See `01-supervisor.md` for the implementation stub.)
- **Container restart.** Entire tmpfs clears — ultimate fallback.

### Why not cap-and-inline

Keeping two paths (small = base64 in frame, large = side-channel) means every caller has to branch on the response shape. One path is easier to reason about, easier to test, and the extra tmpfs write for a small attachment is effectively free on tmpfs (in-memory).

---

## Dependencies

- **Email broker:** stdlib `imaplib` (sync; we wrap in a worker thread), stdlib `smtplib`, stdlib `email` for MIME construction and parsing.
- **Calendar broker:** `caldav` library (pip), `icalendar` for iCal parsing. Both add to `pyproject.toml`.

Both brokers import the shared `brokers._common` package for RPC, ready-signaling, and exit-code constants.

---

## Implementation milestones

1. `_common/_rpc.py` + unit tests on frame encoding/decoding.
2. `email_broker` IMAP path against a real IMAP stub (the stdlib has `imaplib` and `email`; we can stand up a local fake).
3. `email_broker` SMTP path against a local fake SMTP server (either extend the fake in `fake_email.py` or use `aiosmtpd`).
4. `calendar_broker` against a fake DAV server (`radicale` in a pytest fixture).
5. Exit-code handling — simulate IMAP auth failure, SMTP auth failure, connection loss.
6. End-to-end: supervisor spawns, broker connects to a real Gmail test account (manual smoke test covering search + send + calendar).

---

## Testing notes

Strategy in [`09-testing.md`](09-testing.md). Component-specific scope:

- **Email broker** tests spawn the real broker subprocess against `tests/fixtures/fake_email.py` — an asyncio process that serves both an RFC-3501-subset IMAP endpoint and an RFC-5321-subset SMTP endpoint on two port-0 sockets. Broker talks to it over real TCP; tests talk to the broker over real UDS.
  - IMAP verbs: `list_mailboxes`, `search_messages`, `fetch_message`, `fetch_headers`, `flag_message`, `move_message` — one behavior test each.
  - SMTP verb: `send_message` round-trip — broker assembles MIME, SMTP fake records the submission, test asserts headers/body/attachments match and a Message-ID is returned.
  - Auth: three consecutive IMAP LOGIN rejections → broker exits 77. Three consecutive SMTP AUTH rejections (across separate `send_message` calls) → broker exits 77.
  - Reconnect: fake drops IMAP TCP mid-session → broker reconnects transparently, next verb succeeds.
  - **Write enforcement**: broker spawned with `WRITE_ALLOWED=false` → `flag_message`, `move_message`, `send_message` each return `{"error":{"code":"WRITE_DENIED"}}` and `fake_email.py` observes zero `STORE`/`MOVE`/`DATA` traffic. Respawn with `WRITE_ALLOWED=true` → same verbs succeed.
- **Calendar broker** tests spawn the real broker subprocess against a `radicale` instance started in a pytest fixture on port 0.
  - Verbs: `list_calendars`, `list_events`, `get_event`, `create_event`, `update_event`, `delete_event` — one behavior test each.
  - ETag round-trip: `create_event` → `update_event` with stale etag → `If-Match` 412 → broker surfaces as `UPSTREAM`.
  - **Write enforcement**: broker spawned with `WRITE_ALLOWED=false` → `create_event`, `update_event`, `delete_event` each return `WRITE_DENIED` and radicale observes no `PUT` / `DELETE`. Respawn with the flag flipped → writes succeed.
- Keep `imaplib` / `smtplib` / `caldav` calls in `_imap_session.py` / `_smtp_session.py` / `_session.py` so the broker is easy to test — but the test point is **the broker as a subprocess**, not the session module in isolation. Mocking stdlib directly is discouraged; extend `fake_email.py` instead.
- Real Gmail is a manual PR-checklist smoke test, not CI (see `09-testing.md` "Out of scope").
- Pure-unit coverage (`@pytest.mark.unit`): MIME assembly for `send_message` (attachments, inline HTML, UTF-8 subjects, threading headers `In-Reply-To` / `References`), and iCalendar ↔ JSON translation edge cases (recurring events, all-day, timezone handling) — both lossy-by-accident and worth isolating.

---

## Component-local open items

- **IMAP APPEND for non-Gmail providers.** When we ship Fastmail/iCloud support, `send_message` must also APPEND the raw message to the Sent mailbox (those providers don't auto-save like Gmail does). Deferred.
- **Calendar-color handling.** Gmail CalDAV color metadata is non-standard; might need per-provider normalization in `07-catalog.md`.
- **Rate limiting.** Gmail will throttle excessive IMAP searches or rapid SMTP sends. Broker should surface 429-equivalents as `NETWORK` with a hint. Implementation deferred.
- **IMAP connection pool.** If real traces show contention from the single-session serialization lock, revisit with a small pool of N IMAP sessions sharing a single LOGIN-on-boot cost. Not needed for v1 scale.
- **Verb set deliberately omitted.** `APPEND` (for draft management), IMAP `IDLE` (push vs poll), custom threading, server-side mailbox creation, mailbox subscriptions, quota queries. Each can be added later if a real need surfaces.
