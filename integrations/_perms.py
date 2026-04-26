"""Canonical filesystem permission policy for the integrations subsystem.

Two distinct mechanisms enforce these modes — they MUST agree:

1. **Container entrypoint** (``container/entrypoint.sh``, runs as root before
   any process drops privilege): chowns the directory layout and sets the
   directory modes. The bash literals there must match the constants below.
2. **Process-level chmods** (this file): every Python ``chmod`` call inside
   the supervisor and brokers references the constants below, never a magic
   number. ``os.umask(_PROCESS_UMASK)`` is set at the top of each process's
   ``__main__`` so any file or directory the process creates without an
   explicit mode is also owner-only by default.

The trust split the modes encode:
- Vault contents (``.master-key``, ``creds/*.{meta,enc}``) are readable only
  by the broker UID. The agent (computron UID) cannot decrypt credentials
  even with full filesystem access to the rest of the container.
- Runtime sockets (``app.sock`` and per-broker sockets under ``/run/cvault/``)
  are readable + writable by the broker UID and the broker GROUP. Computron
  is in the broker group purely to connect to these sockets — nothing else.

If you change a constant here, audit ``container/entrypoint.sh`` for the
matching directory chmod and update both in lockstep.
"""

from __future__ import annotations

# Owner-only files: master key, encrypted credential bundles, .meta envelopes.
# Permitted only for the broker UID; group and other get nothing.
VAULT_FILE_MODE = 0o600

# Owner-only directories: vault root and any sub-tree the supervisor creates
# inside it (e.g. ``creds/``).
VAULT_DIR_MODE = 0o700

# Sockets the app server needs to connect to. broker UID owns the file; the
# computron UID reaches it via broker-group membership. Other UIDs are blocked
# at the kernel by EACCES before any of our code runs.
SOCKET_MODE = 0o660

# Runtime directory holding the sockets above. Mode 0o750 lets group members
# (computron) traverse to reach the sockets — write is broker-only.
RUNTIME_DIR_MODE = 0o750

# Process-wide umask the supervisor and brokers install at startup. ``0o077``
# masks every group/other bit, so any subsequent ``mkdir`` / ``open`` /
# ``write`` produces an owner-only result by default. Explicit chmod calls
# (above) still apply where a specific mode is needed (notably 0o660 sockets,
# which umask cannot widen back open).
PROCESS_UMASK = 0o077
