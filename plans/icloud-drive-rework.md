# iCloud Drive Rework

Replace pyicloud-based auth with direct Apple API calls. Use rclone env vars instead of config file.

## Changes

### 1. Rewrite: `integrations/_icloud_auth.py`
Replace pyicloud with direct aiohttp calls to Apple's signin/2FA endpoints.
- `initiate_auth(email, password)` → signin, triggers 2FA, returns `{session_id, requires_2fa}`
- `complete_auth(session_id, code)` → validates 2FA, returns `{trust_token}`
- No filesystem writes — just returns the trust_token
- No pyicloud dependency — uses aiohttp (already in project)
- All functions are now async

### 2. Update: `integrations/supervisor/_catalog.py`
Update icloud_drive BrokerSpec:
- `static_env`: `RCLONE_CONFIG_DEFAULT_TYPE = iclouddrive`
- `env_injection`: `email → RCLONE_CONFIG_DEFAULT_USER`, `trust_token → RCLONE_CONFIG_DEFAULT_TRUST_TOKEN`

### 3. Update: `integrations/supervisor/_manager.py`
- `reauth_init`: now `await initiate_auth(...)` (async)
- `reauth_verify`: now `await complete_auth(...)`, updates `trust_token` in vault secrets, respawns broker

### 4. Update: `server/_icloud_drive_routes.py`
- `handle_preauth_icloud_drive`: now `await initiate_auth(...)`
- `handle_preauth_icloud_drive_verify`: now `await complete_auth(...)`, returns `{trust_token}`

### 5. Update: `server/ui/src/components/integrations/AddIntegrationModal.jsx`
- `doAddIntegration` now accepts `trustToken` param
- For icloud_drive: sends `{email, trust_token}` in auth_blob
- For other providers: sends `{email, password}` as before
- `handleTwoFactorSubmit`: passes `verifyBody.trust_token` to `doAddIntegration`

### 6. No changes needed:
- `server/aiohttp_app.py` — routes unchanged
- `integrations/brokers/rclone_broker/` — unchanged, reads env vars
- `integrations/supervisor/_spawn.py` — unchanged, injects env vars from secret_bundle
- No pyicloud in requirements — never was

### Flow
```
Web UI:
  1. User enters Apple ID + password
     → POST /api/integrations/preauth/icloud-drive
     → Apple signin, 2FA triggered
     ← {session_id, requires_2fa: true}

  2. User enters 2FA code
     → POST /api/integrations/preauth/icloud-drive/verify
     → Apple validates code
     ← {trust_token: "..."}

  3. Normal add flow:
     → POST /api/integrations
     auth_blob: {email, trust_token}

Supervisor:
  4. write_secrets({email, trust_token})
  5. spawn_broker with env:
     RCLONE_CONFIG_DEFAULT_TYPE=iclouddrive
     RCLONE_CONFIG_DEFAULT_USER=<email>
     RCLONE_CONFIG_DEFAULT_TRUST_TOKEN=<token>
  6. rclone about default: → works
```