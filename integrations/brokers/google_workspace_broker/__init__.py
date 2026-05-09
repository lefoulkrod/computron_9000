"""Broker for Google Workspace integrations (Gmail, Calendar, Drive, Contacts).

Spawned by the supervisor when an integration with slug ``google_workspace``
is added or reconciled. Auth: OAuth 2.0 authorization-code flow with a
loopback redirect — user supplies their own GCP OAuth client credentials
(BYO project), the app server runs the redirect handshake, and the
supervisor encrypts the resulting tokens and hands them to this broker
via env at spawn time.

This package's ``__main__`` is the entry point. The broker holds the access
token + refresh token in memory and reaches the Google APIs over HTTPS.
Token refresh happens transparently when the access token expires; an
unrecoverable refresh failure surfaces as exit 77 so the supervisor flips
state to ``auth_failed``.
"""
