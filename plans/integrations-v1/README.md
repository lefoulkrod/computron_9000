# Integrations v1 — Plan Index

The overall design is in [`plan.md`](plan.md). The UI mockup (onboarding flow) is [`onboarding.html`](onboarding.html).

Each P0 deliverable is specified in its own sub-plan:

- [`01-supervisor.md`](01-supervisor.md) — crypto, master key, spawn + lifecycle, `app.sock` RPC
- [`02-broker-email-calendar.md`](02-broker-email-calendar.md) — email broker (IMAP + SMTP) and calendar broker (CalDAV)
- [`03-broker-mcp.md`](03-broker-mcp.md) — generic stdio MCP subprocess host
- [`04-auth-plugins.md`](04-auth-plugins.md) — declarative `FIELDS` + `ENV_INJECTION` contract
- [`05-api-and-client.md`](05-api-and-client.md) — `/api/integrations/*` routes + `broker_client`
- [`06-ui.md`](06-ui.md) — React Integrations tab
- [`07-catalog.md`](07-catalog.md) — catalog JSON schema + v1 provider entries
- [`08-container.md`](08-container.md) — Dockerfile, entrypoint, volume layout
- [`09-testing.md`](09-testing.md) — testing strategy + the three test doubles

## Build order suggestion

The sub-plans are numbered roughly in dependency order, but the critical path looks like:

1. **Container + Supervisor scaffold** (08 + 01, minus brokers) — vault dir exists, supervisor boots as UID 1001, `app.sock` works. No brokers yet; just the empty shell.
2. **First broker + first auth plugin** (02 IMAP + 04 `app_password`) — end-to-end proof that spawn + env injection + verify works. Uses a test IMAP account.
3. **API + client** (05) — app server can list/add/verify integrations; `broker_client.call()` reaches brokers.
4. **Catalog + UI** (07 + 06) — user-facing surface comes alive.
5. **Second broker kind** (03 MCP + the remaining auth plugins) — proves the broker model is genuinely generic.

## How to add a new provider, post-v1

1. Drop a file in `config/integrations_catalog/<slug>.json`.
2. Reference an existing `auth_plugin` (`app_password`, `api_key`, `mcp_subprocess`).
3. Point at an existing broker command (`email_broker`, `calendar_broker`, `mcp_broker`).
4. Ship.

No new Python. No new broker code. That's the whole point of the decomposition.
