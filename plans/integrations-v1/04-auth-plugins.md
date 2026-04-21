# 04 — Auth Plugins

> Tiny declarative modules that tell the rest of the system: "here's the form the user fills in, here's how those fields become broker env vars." No executable verify code — the broker's first spawn IS the verify.

---

## Purpose

Describe the bootstrap surface for each auth style without writing per-provider code. Adding a new IMAP/CalDAV provider or a new MCP server should NOT require a Python function; it should be a catalog JSON entry that references an existing auth plugin.

---

## Code layout

```
auth_plugins/
├── __init__.py            # facade — loads each plugin by name
├── types.py               # Field, AuthBlob, EnvInjection pydantic models (no deps)
├── app_password.py        # email + app-password (v1)
├── api_key.py             # single token / PAT / API key (v1)
└── mcp_subprocess.py      # multi-field bundle for MCP servers (v1)
```

Each plugin module exposes exactly two top-level names: `FIELDS` and `ENV_INJECTION`. Plus the module name itself is the plugin ID referenced from catalog entries.

---

## The contract

```python
# auth_plugins/types.py

from typing import Literal
from pydantic import BaseModel

class Field(BaseModel):
    name: str                                # e.g. "password"
    label: str                               # shown in the wizard
    type: Literal["text", "email", "password", "url", "token"]
    required: bool = True
    placeholder: str | None = None
    hint: str | None = None
    pattern: str | None = None               # regex; client + server validation
    deep_link: str | None = None             # e.g. "https://myaccount.google.com/apppasswords"
    deep_link_label: str | None = None       # e.g. "Open Google app-passwords page"
    strip: str | None = None                 # characters to strip before storing (e.g. " ")
    min_length: int | None = None
    max_length: int | None = None
```

```python
# auth_plugins/app_password.py

from auth_plugins.types import Field

FIELDS = [
    Field(
        name="email",
        label="Email address",
        type="email",
        placeholder="you@gmail.com",
    ),
    Field(
        name="password",
        label="App password",
        type="password",
        placeholder="16 letters, spaces optional",
        pattern=r"^[a-z\s]{16,20}$",
        strip=" ",
        deep_link="https://myaccount.google.com/apppasswords",
        deep_link_label="Open Google app-passwords page",
    ),
]

# Map from field name → broker env-var name
ENV_INJECTION = {
    "email":    ["IMAP_USER", "CALDAV_USER"],
    "password": ["IMAP_PASS", "CALDAV_PASS"],
}
```

That's the entire plugin. No verify function, no bootstrap flow code.

---

## v1 plugins

### `app_password`

Used by: Gmail (v1), Fastmail (P1), iCloud (P1), Outlook.com consumer (P1), Custom IMAP/CalDAV (P1).

- `FIELDS`: `email`, `password` (plus an optional `label` handled at the integration level, not here).
- `ENV_INJECTION` maps password → both `IMAP_PASS` and `CALDAV_PASS` (same app password authenticates both).

### `api_key`

Used by: generic bearer-token integrations where the broker is MCP-based. Typically catalog entries that launch an MCP server expecting a single `*_TOKEN` env var.

- `FIELDS`: one `token` field with a provider-specific deep-link (GitHub PAT page, Linear API keys page, Notion integration page, etc.).
- `ENV_INJECTION`: `{ "token": [<env-var from catalog>] }`. The catalog entry supplies the env-var *name* (e.g., `GITHUB_PERSONAL_ACCESS_TOKEN`).

### `mcp_subprocess`

Used by: any MCP server whose config needs more than one field (Home Assistant needs URL + token; Notion needs a workspace ID + token; etc.).

- `FIELDS`: dynamically composed from the catalog entry's declared fields. The plugin itself declares no fixed FIELDS — instead the catalog entry's `config_fields` section is spliced in directly.
- `ENV_INJECTION`: passthrough — each declared field maps to its named env var.

This is the only plugin that is "dynamic"; the other two have fixed FIELDS and cover the common cases.

---

## The add flow

```
UI                         app server                     supervisor                  broker
──                         ──────────                     ──────────                  ──────
GET /api/integrations/
    catalog/<slug>         → reads catalog + auth plugin
                           → returns FIELDS to render
POST /api/integrations
  {slug, suffix, label,
   fields: {...}}          → app-server validates fields
                             against FIELDS pydantic schema
                           → normalizes (strips, etc.)
                           → sends ADD {blob} over
                             app.sock                       → encrypts to
                                                              <id>.enc.tmp
                                                           → computes env from
                                                              ENV_INJECTION
                                                           → spawn broker                 → connect upstream
                                                           ← waits for READY or exit        → READY OR exit 77
                                                           → rename .tmp → .enc
                                                             OR delete .tmp
                           ← returns {id, state,
                                      state_reason?}
                                                                                       
← UI shows new integration
  row with the final state
```

The **only** per-provider code in this flow is the auth plugin's two declarations. Validation, transport, encryption, spawn, verify all reuse shared infra.

---

## How FIELDS are consumed

### By the UI

`05-api-and-client.md` exposes `GET /api/integrations/catalog/<slug>` which returns the merged catalog entry + auth plugin FIELDS. UI iterates the list and renders one form control per field using `type` to pick the widget.

### By the app server

`field.pattern`, `field.required`, `field.min_length`, `field.max_length` are enforced on the POST body. Pydantic model generated per-field.

### By the supervisor

`ENV_INJECTION` is applied post-validation. The supervisor never re-validates against FIELDS; that's the app server's job.

---

## How to add a new auth plugin

1. Create `auth_plugins/<name>.py`.
2. Define `FIELDS` and `ENV_INJECTION`.
3. Reference `<name>` in one or more catalog entries' `auth_plugin` field.
4. No code changes anywhere else.

Example: adding `yahoo_app_password` — same FIELDS as `app_password` but a different deep-link. Actually, the plugin doesn't need to be duplicated; the catalog entry can override deep links (see `07-catalog.md`). So in practice, we rarely add new plugins; we add new catalog entries.

---

## Where OAuth will land (P2)

An `oauth2_pkce` plugin will be added post-v1. Schema sketch:

```python
FIELDS = [
    Field(name="_connect_button", label="Connect with Google", type="...special..."),
]
ENV_INJECTION = {
    "access_token": [...],
    "refresh_token": [...],
}
```

The special "button" field type triggers a browser-based OAuth flow; the returned tokens populate the blob as if they were user-entered fields. Details deferred.

---

## Dependencies

- `pydantic` (already in the project).
- No new pip packages.
- No runtime subprocess / network work at the plugin level.

---

## Implementation milestones

1. `types.py` with `Field` model + unit tests on regex/strip/length validation.
2. `app_password.py` — the Gmail path. Test by generating a JSONSchema and rendering a fake wizard.
3. `api_key.py` — the GitHub path.
4. `mcp_subprocess.py` — dynamic FIELDS merging logic.
5. Integration with `05-api-and-client.md`'s `/catalog/<slug>` endpoint.

---

## Testing notes

- All tests unit-only. Each plugin's module is data + a tiny amount of validation.
- Golden tests: snapshot the JSON returned by `/api/integrations/catalog/gmail` to catch accidental FIELDS drift.

---

## Component-local open items

- **Field order.** `FIELDS` is a list; order is preserved. Good enough for v1. If we later want grouped/sectioned forms, add a `section` attribute.
- **Conditional fields.** E.g., "if provider=Fastmail, show optional CalDAV URL override." Can be modeled by catalog-level field overrides. Not a v1 concern.
- **Client-side secret handling.** Password fields should render with `type="password"` in the browser, never be logged, never persist in browser storage. Enforced in UI code (`06-ui.md`).
