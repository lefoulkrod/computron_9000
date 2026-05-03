"""Supervisor: the credential-owning trusted process.

Runs as a dedicated UID, holds the master key for the credential vault, and
spawns + manages subprocess helpers (brokers today; potentially proxies for
LLM provider keys or other credential-bearing roles later). The app server
communicates with the supervisor over a Unix Domain Socket to add, list,
resolve, and remove integrations, but never reads the decrypted credentials
itself.
"""
