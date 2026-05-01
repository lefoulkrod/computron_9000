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

This module also exposes :func:`disable_core_dumps`, a startup-time
hardening helper for the supervisor and brokers. Core dumps would write
the process's full memory snapshot — credentials included — to disk
where another UID could read it; setting ``RLIMIT_CORE=(0, 0)`` tells
the kernel never to generate one for this process or its children.
"""

from __future__ import annotations

import resource

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

# Email-attachment files written by the broker into the shared downloads dir.
# Owner (broker) rw, group (broker — which computron is in) r, others none.
# Group read is what lets the computron-UID side open these files.
ATTACHMENT_FILE_MODE = 0o640

# Process-wide umask the supervisor and brokers install at startup. ``0o077``
# masks every group/other bit, so any subsequent ``mkdir`` / ``open`` /
# ``write`` produces an owner-only result by default. Explicit chmod calls
# (above) still apply where a specific mode is needed (notably 0o660 sockets,
# which umask cannot widen back open).
PROCESS_UMASK = 0o077


def disable_core_dumps() -> None:
    """Set ``RLIMIT_CORE = (0, 0)`` so the kernel won't dump this process.

    Call once at the top of the supervisor and broker ``__main__`` modules.
    Brokers hold the decrypted credential in memory; a crash with the
    default core-dump policy would write that memory to disk where the
    computron UID could read it (the dump file inherits the dumping
    process's UID, but the path and permissions can leak depending on
    ``/proc/sys/kernel/core_pattern``). Hard-capping at zero closes the
    leak path entirely.

    Subprocesses inherit the rlimit, so brokers spawned by the supervisor
    are covered without needing their own call — but each broker calls it
    again anyway for defense in depth and so a broker started outside the
    supervisor (manual debugging, future test harnesses) is also covered.
    """
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
