# 07 — Integration Catalog

> Static JSON files — one per provider — that tell the rest of the system which auth plugin to use, which broker to spawn, which category to show it under, and what to prefill.

---

## Purpose

Keep per-provider knowledge out of code. Adding Fastmail, Home Assistant, Notion, etc. after v1 should be a one-file PR with zero Python changes.

---

## Location

```
config/integrations_catalog/
├── gmail.json
├── github.json
└── (fastmail.json, homeassistant.json, notion.json, linear.json, … as we curate)
```

Bundled with the app image at `/app/config/integrations_catalog/`. Read by the supervisor at startup and by the app server's `/api/integrations/catalog` endpoint.

---

## Schema

```jsonc
{
  "schema_version": 1,
  "slug": "gmail",                        // URL-safe, matches filename
  "label_default": "Gmail",               // pre-fills the wizard label field
  "category": "email_calendar",           // email_calendar | dev_tools | smart_home | productivity | custom
  "icon": "bi-envelope-at",               // bootstrap-icons name
  "kinds": ["imap", "caldav"],            // list of broker kinds to spawn (one for MCP, one/two for email-calendar)
  "auth_plugin": "app_password",          // references auth_plugins/<name>.py
  "field_overrides": {                    // optional: tweak the auth plugin FIELDS for this provider
    "password": {
      "deep_link": "https://myaccount.google.com/apppasswords",
      "deep_link_label": "Open Google app-passwords page",
      "hint": "16 lowercase letters. Spaces are OK."
    }
  },
  "brokers": [
    {
      "kind": "imap",
      "command": ["python", "-m", "brokers.imap_broker"],
      "env": {
        "IMAP_HOST": "imap.gmail.com",
        "IMAP_PORT": "993"
      }
    },
    {
      "kind": "caldav",
      "command": ["python", "-m", "brokers.caldav_broker"],
      "env": {
        "CALDAV_URL": "https://apidata.googleusercontent.com/caldav/v2"
      }
    }
  ],
  "tools_exposed": [                      // for UI display; also used by dynamic tool descriptions
    "search_email",
    "fetch_message",
    "list_events",
    "create_event",
    "delete_event"
  ],
  "docs_url": "https://support.google.com/accounts/answer/185833",
  "advisory": null                        // optional warning banner text, e.g. "Workspace accounts not supported"
}
```

### MCP-flavored example

```jsonc
{
  "schema_version": 1,
  "slug": "github",
  "label_default": "GitHub",
  "category": "dev_tools",
  "icon": "bi-github",
  "kinds": ["mcp"],
  "auth_plugin": "api_key",
  "field_overrides": {
    "token": {
      "label": "GitHub personal access token",
      "deep_link": "https://github.com/settings/tokens?type=beta",
      "deep_link_label": "Open GitHub PAT page",
      "hint": "Fine-grained PAT with repo scope. Paste here."
    }
  },
  "brokers": [
    {
      "kind": "mcp",
      "command": ["python", "-m", "brokers.mcp_broker"],
      "env": {
        "MCP_COMMAND": "uvx",
        "MCP_ARGS": "[\"github-mcp\"]",
        "MCP_ENV_OVERRIDES": "{\"GITHUB_PERSONAL_ACCESS_TOKEN\": \"__INJECT__\"}"
      }
    }
  ],
  "token_env_var": "GITHUB_PERSONAL_ACCESS_TOKEN",   // for api_key plugin's ENV_INJECTION map
  "tools_exposed": ["__dynamic__"],
  "docs_url": "https://github.com/modelcontextprotocol/github-mcp"
}
```

The MCP case uses a small amount of indirection:

- The catalog entry says "run this MCP server with this env layout."
- The auth plugin (`api_key`) takes the user's token and fills in the `__INJECT__` placeholder at spawn.
- `tools_exposed: ["__dynamic__"]` signals the UI / supervisor to fetch the actual tool list from the broker after it's running.

---

## v1 entries

Two files, matching the plan's v1 slate:

| File | Provider | Auth | Broker kinds |
|---|---|---|---|
| `gmail.json` | Gmail consumer | `app_password` | `imap` + `caldav` |
| `github.json` | GitHub | `api_key` | `mcp` (via `uvx github-mcp`) |

---

## How the pieces compose

```
wizard                       app server                  supervisor             broker
──────                       ──────────                  ──────────             ──────
user picks "Gmail"
GET catalog/gmail      →     read gmail.json
                             merge with auth_plugins/
                               app_password.py FIELDS
                             apply field_overrides
                       ←     merged form spec
user submits form
POST integrations      →     validate against FIELDS
                             normalize
                             send ADD over app.sock   →  encrypt blob
                                                         for each entry in catalog.brokers:
                                                           merge broker.env + ENV_INJECTION → full env
                                                           spawn broker                       → connect
                                                         wait for all READY                   → READY
                                                         rename .tmp → .enc
                       ←     return {id, state}       ←  return {id, state}
```

---

## Advisory / deprecation notes

`advisory` is free-form text shown in the wizard as a warning banner. Examples:

- `"Requires 2-Step Verification turned on in your Google account."` (gmail.json)
- `"Workspace accounts must use OAuth (not yet supported in Computron)."` (on the outlook365 placeholder, if we add it)

Not rendered as an error — it's a heads-up, not a blocker.

---

## Multi-kind integrations

When a catalog entry has `kinds: ["imap", "caldav"]`, the supervisor spawns **two brokers** with a shared integration_id but distinct socket names (`<id>.imap.sock`, `<id>.caldav.sock`). The broker_client's `resolve()` takes an optional `kind_hint` to pick between them (default = first kind). Tool handlers that only use IMAP pass `kind_hint="imap"`; calendar tools pass `kind_hint="caldav"`.

---

## How to add a new provider (post-v1)

1. Write `config/integrations_catalog/<slug>.json`.
2. If no existing auth plugin fits, write one (rare — `app_password`, `api_key`, `mcp_subprocess` cover almost everything).
3. Ship.

That's it. No code changes in supervisor, brokers, or client.

---

## Validation

A Pydantic model (`catalog.CatalogEntry`) validates each file at startup. Errors fail loud — the supervisor refuses to start if any catalog file is malformed rather than silently skipping it. Bad catalog JSON is a bug, not a runtime condition.

---

## Dependencies

- Only stdlib JSON + Pydantic. No new pip packages.

---

## Implementation milestones

1. `catalog/types.py` with `CatalogEntry` pydantic model.
2. `catalog/_loader.py` — scan dir, parse, validate, cache.
3. `gmail.json` + `github.json` as v1 entries.
4. `/api/integrations/catalog` and `/api/integrations/catalog/:slug` endpoints.
5. Wizard rendering against the merged catalog+plugin spec.

---

## Testing notes

- Golden tests on the merged-spec JSON to catch accidental drift.
- Pydantic validation tests for required fields, URL/slug format, auth_plugin existence check.

---

## Component-local open items

- **Registry model.** v1 ships the catalog with the app image; updates require a new release. Post-v1, consider a signed registry URL with per-entry SHA256 pinning. Not urgent.
- **Icon set.** Bootstrap Icons covers most providers. For truly unique brand marks (Home Assistant's logo?), we may want SVG icons in-repo. Defer.
- **i18n for labels.** English-only in v1. `label_default` and `hint` are English strings; revisit if we internationalize the rest of the app.
