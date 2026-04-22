# 09 — Testing Strategy

> How we test the integrations subsystem. One rule: **mock only at the external-network boundary.** Everything inside the container runs for real.

---

## Philosophy

- **Tests constrain behavior, not implementation.** A good test survives a refactor of the code under it. If a refactor forces a bunch of test rewrites, the tests were bound to internals.
- **Mock at a boundary you want to keep stable.** External service APIs (IMAP, CalDAV, an MCP server's upstream) are real contracts not owned by us — mocking them is fine. Subprocess spawn, UDS sockets, and file I/O are not boundaries; they're how the design works. Mocking them hides bugs.
- **Unit tests have a place.** Pure-function behavior that genuinely warrants isolation (crypto round-trip, frame encode/decode, exception mapping) is fine at unit-level. The rule is "what's worth a unit test," not "no unit tests."
- **"Integration" here ≠ slow.** Each integration test targets sub-second runtime. Fakes live in-process or as short-lived local subprocesses. Whole suite stays under a minute at v1 scale.

---

## What's real in tests

- Subprocess spawn (`fork` + `exec`).
- Unix Domain Sockets (kernel sockets, real `SO_PEERCRED`).
- The file system (`tmp_path` per test; real `chmod` / ownership within the test UID).
- AES-GCM encryption / decryption.
- JSON frame encoding + length-prefix framing.
- Process exit codes + signal handling.
- The supervisor's `app.sock` RPC.

## What's mocked

- **External network only** — any socket to an IP outside the test process. IMAP server on the internet, CalDAV server on the internet, MCP server's upstream API. Replaced with the three test doubles below.

---

## The three test doubles

### 1. `FakeBroker` — drop-in broker for supervisor tests

`tests/fixtures/fake_broker.py`. Reads `INTEGRATION_ID` and `BROKER_SOCKET` from env (same contract as a real broker), binds the UDS, prints `READY\n`, serves length-prefixed JSON frames. Behavior toggled by env:

| Env var | Effect |
|---|---|
| `FAKE_AUTH_FAIL=startup` | Exit 77 before printing READY (startup auth failure). |
| `FAKE_AUTH_FAIL=midstream` | Print READY, then exit 77 after the first verb call. |
| `FAKE_SLOW_READY=5` | Delay 5 s before printing READY (timeout tests). |
| `FAKE_CRASH_AFTER_N=3` | Exit 1 after the Nth verb call (backoff tests). |
| `FAKE_ECHO_VERBS=1` | Echo args back as result (happy-path). |
| `FAKE_RETURN_AUTH_ERROR=1` | Respond `{"error":{"code":"AUTH"}}`, stay alive (transient-error simulation — state should *not* flip). |

Supervisor tests point the catalog-entry's `broker_cmd` at this script via a fixture.

### 2. Fake upstream services for broker tests

- **Email (IMAP + SMTP):** `tests/fixtures/fake_email.py` — single asyncio process that runs **both** an RFC-3501-subset IMAP server (for `LOGIN`, `LIST`, `SELECT`, `SEARCH`, `FETCH`, `STORE`, `MOVE`) and an RFC-5321-subset SMTP server (for `EHLO`, `AUTH`, `MAIL FROM`, `RCPT TO`, `DATA`, `QUIT`) on two port-0 sockets. Deterministic state: in-memory mailboxes + in-memory outbox seeded by the test. Broker's `imaplib` and `smtplib` talk to it on localhost.
- **CalDAV:** `radicale` started in a pytest fixture on a random port. Real CalDAV server, pip-installable, in-process. Broker's `caldav.DAVClient` talks to it over real HTTP.
- **MCP:** `tests/fixtures/stub_mcp_server.py` — standalone script speaking MCP (JSON-RPC 2.0 over stdio). Implements `initialize`, `tools/list`, `tools/call`. Env-configurable:

| Env var | Effect |
|---|---|
| `STUB_MCP_TOOLS=<json>` | Tool list returned by `tools/list`. Each tool can declare `readOnlyHint`, `destructiveHint`. |
| `STUB_MCP_AUTH_FAIL=1` | Return empty tools/list (the MCP-broker's auth-failure sentinel → exit 77). |
| `STUB_MCP_HANG=5` | Sleep 5 s before responding to `initialize`. |
| `STUB_MCP_CALL_ERROR=<json>` | On any `tools/call`, return this error frame. |

### 3. `StubBroker` — in-process UDS stub for `broker_client` tests

`tests/fixtures/stub_broker.py`. Tiny asyncio UDS server inside the test process; returns pre-programmed frames for pre-programmed verb names. No subprocess. Used only for testing `broker_client` logic (resolve caching, write-verb gate, exception mapping) where spawning a subprocess adds cost without adding coverage.

---

## Test tiers per component

| Layer | Style | Representative tests |
|---|---|---|
| **Supervisor** (`broker_supervisor/`) | Integration: real supervisor, `tmp_path` vault, `FakeBroker` children. | Exit 77 → state flips `auth_failed`, no restart. Orphan `.enc` at startup → logged and skipped. `set_permissions` rewrites `.meta` without loading the master key **and respawns the broker** (assertable by the `FakeBroker` PID changing and the new process's env containing the updated `WRITE_ALLOWED` flag). Backoff schedule (1 s → 5 s → 30 s → 5 m) observed on an exit-1 loop. `SO_PEERCRED` rejects a non-`computron` UID (via env override; see Sharp edges). |
| **Email broker / calendar broker** (`brokers/email_broker/`, `brokers/calendar_broker/`) | Integration: real broker subprocess + fake upstream + real UDS. | `search_messages` returns UIDs matching query. `flag_message` issues correct `STORE`. `send_message` round-trips through the SMTP fake. 3 reconnect-auth-fails (IMAP or SMTP) → broker exits 77. `list_calendars` parses a real radicale principal. `create_event` round-trips an iCalendar event. **`WRITE_ALLOWED=false` spawn → every write verb returns `WRITE_DENIED` locally without touching upstream** (assert by observing no TCP connect on the SMTP fake when `send_message` is called). |
| **MCP broker** (`brokers/mcp_broker/`) | Integration: real broker subprocess + `stub_mcp_server.py` + real UDS. | Empty `tools/list` from stub → broker exits 77. `tools/call` passthrough preserves request IDs. SIGTERM → broker shuts the subprocess down within grace window. Stub hanging on `initialize` → broker respects `MCP_INITIALIZE_TIMEOUT`. **`WRITE_ALLOWED=false` spawn → `tools/call` for a tool without `readOnlyHint=true` returns a JSON-RPC error locally; stub never receives the call. Tool with `readOnlyHint=true` is forwarded normally. After `notifications/tools/list_changed` the read-only map refreshes and the new tools' enforcement respects the current flag.** |
| **broker_client** (`broker_client/`) | Unit-ish: `StubBroker` in-process, no subprocess. | Write verb + `write_allowed=false` → `IntegrationWriteDenied` raised before UDS open. Broker `AUTH` error → `IntegrationAuthFailed`. Resolve cache honored within the 500 ms window and refreshed after. |
| **App-server routes** (`server/routes/integrations.py`) | Integration: real supervisor + `FakeBroker` children + aiohttp test client. | `POST /api/integrations` happy path returns `active`. `PATCH write_allowed` triggers a supervisor state-change event. 409 on auth failure includes `state_reason`. `GET` omits anything resembling cred values. |
| **MCP bridge** (`server/mcp_bridge.py`) | Integration: real bridge + MCP broker + `stub_mcp_server.py`. | Tool with `readOnlyHint=true` registered regardless of `write_allowed`. Write-tagged tool skipped when `write_allowed=false`. Re-registration happens on `write_allowed` flip. Request-ID rewriting survives a round-trip. |
| **Pure unit** (small, few) | In-process, no subprocesses or sockets. | Crypto round-trip + tamper detection (flip a ciphertext byte → decrypt raises). Frame encode/decode edge cases. Pydantic model validation for `IntegrationMeta` and catalog entries. `_VERB_TYPES` const in `broker_client` diffed against the table in `02-broker-email-calendar.md` (so drift fails loud). |

---

## Sharp edges

- **`SO_PEERCRED` under test.** Tests run as a single UID, so we can't organically exercise "refuse non-`computron` UID." The supervisor reads its expected peer-UID from `COMPUTRON_APP_UID` (defaults to 1000 in prod). Tests set it to the test-process UID for happy-path and to a different value for the rejection test.
- **Subprocess cleanup on failure.** Every fixture wraps start/stop in try/finally (or pytest's `yield`-then-teardown) to SIGTERM + `wait` with a timeout. A session-level fixture asserts no lingering test-spawned children at the end — if one survives, the test file owns a bug.
- **`tmp_path` per test.** Every test gets its own vault dir. No shared state across tests. Supervisor's `0700` mode assertion runs on a dir the test just created, so the assertion holds naturally.
- **CI timing.** Each subprocess test has a ≥ 5 s timeout on "broker ready." Slower CI runners are fine; only runaway hangs hit the limit.
- **Port collisions (radicale, fake_email's IMAP + SMTP sockets).** Use port `0` to let the kernel pick; pass the bound ports back into the test.

---

## Out of scope for CI

- **Real Gmail / real GitHub MCP.** Manual smoke tests, not CI. Listed in the PR checklist. The account used is a shared test account with an app password rotated quarterly (see `plans/integrations-v1/component_smoke_tests.md` when we write it).
- **Load / stress tests.** One integration at a time is enough for v1. Revisit once we have users with 20+ brokers or an OOM incident.
- **Fuzzing.** Supervisor parses trusted JSON from `app.sock` (peer-cred-checked); brokers parse trusted upstream protocols. Revisit if the threat model expands.

---

## Layout

```
tests/
├── fixtures/
│   ├── fake_broker.py
│   ├── fake_email.py
│   ├── stub_mcp_server.py
│   └── stub_broker.py
├── supervisor/
│   └── test_lifecycle.py
├── brokers/
│   ├── test_imap.py
│   ├── test_caldav.py
│   └── test_mcp.py
├── broker_client/
│   └── test_call.py
└── server/
    ├── test_routes_integrations.py
    └── test_mcp_bridge.py
```

Pytest markers: `@pytest.mark.unit` only for the pure-unit tier. Everything else is unmarked (default). `just test-unit` runs just the marked ones; `just test` runs everything.

---

## Reconciliation with existing project policy

The project's historical stance is "all tests must be unit tests; no Ollama / no external calls." That stance carries forward here as **"no tests against external services."** Tests that spawn local subprocesses, use real UDS, or touch the filesystem in `tmp_path` are not what that rule was trying to prevent — those are cheap, deterministic, and catch exactly the class of bug mock-heavy unit tests have missed in this codebase before. This file supersedes the blanket reading for the integrations subsystem; propagate to the project memory when convenient.

---

## Component-local open items

- **Radicale version pin.** Upstream has occasionally broken CalDAV conformance; pin a known-good major version in dev deps.
- **IMAP fake completeness.** Our fake implements the commands we use. If a broker enhancement later needs `APPEND` or IDLE, extend the fake — don't reach for `imaplib.IMAP4` stubbing.
- **Parallel test runs.** `pytest-xdist` works for the pure-unit tier as-is. Subprocess-tier tests already isolate via `tmp_path` + port-0 binding; verify during implementation.
