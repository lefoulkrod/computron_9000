# iCloud Drive — Auth UI Plan

## Status: DONE

## Overview
Split iCloud Drive into its own integration type (`icloud_drive`) with a
purpose-built 2FA auth flow in the UI.  The existing `icloud` integration
(email/calendar via app-specific password) stays untouched.

## Changes Made

### Backend
1. **`integrations/_icloud_auth.py`** (NEW) — SRP + 2FA handler using pyicloud
   - `initiate_auth(email, password)` → SRP handshake, triggers 2FA, returns session_id
   - `complete_auth(session_id, code)` → validates 2FA, writes rclone config
   - In-memory session store with 10-min TTL

2. **`server/_integrations_routes.py`** — 4 new routes:
   - `POST /api/integrations/preauth/icloud-drive` — initiate auth
   - `POST /api/integrations/preauth/icloud-drive/verify` — complete auth
   - `POST /api/integrations/{id}/reauth` — initiate re-auth (via supervisor)
   - `POST /api/integrations/{id}/reauth/verify` — complete re-auth (via supervisor)

3. **`integrations/supervisor/_app_sock.py`** — 2 new verbs:
   - `reauth_init` → reads password from vault, calls initiate_auth
   - `reauth_verify` → calls complete_auth, respawns broker

4. **`integrations/supervisor/_manager.py`** — `reauth_init()` and `reauth_verify()` methods

5. **`integrations/supervisor/_catalog.py`**:
   - Removed `storage` broker from `icloud` entry (email/calendar only now)
   - Added `icloud_drive` entry with `storage` broker (rclone)

### Frontend
6. **`AddIntegrationModal.jsx`**:
   - Added `icloud_drive` provider (Storage category, "Apple ID + 2FA")
   - Added `TwoFactorStep` component (6-digit code input)
   - Modified wizard flow: icloud_drive skips explainer, goes credentials → 2FA → verify → add
   - CredentialsStep adapts labels for icloud_drive (Apple ID password vs app-specific)

7. **`IntegrationsTab.jsx`**:
   - Added `icloud_drive` to SLUG_META
   - Added "Re-authenticate" button for auth_failed state on icloud_drive
   - Added `ReauthModal` component (auto-initiates reauth, shows 2FA input)

## Flow Summary

### Add flow
```
Provider picker → Credentials (Apple ID + password)
  → POST /preauth/icloud-drive (SRP init, 2FA triggered)
  → 2FA step (user enters code)
  → POST /preauth/icloud-drive/verify (complete SRP, write rclone config)
  → POST /api/integrations (supervisor spawns rclone broker)
  → Success
```

### Re-auth flow
```
Integration card: auth_failed → [Re-authenticate]
  → ReauthModal auto-initiates: POST /{id}/reauth
  → 2FA step (user enters code)
  → POST /{id}/reauth/verify (complete SRP, write new trust token, respawn)
  → Integration returns to "running"
```
