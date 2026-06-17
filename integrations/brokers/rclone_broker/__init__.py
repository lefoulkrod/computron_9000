"""Rclone broker: one process per rclone-backed storage integration.

Launched as ``python -m integrations.brokers.rclone_broker`` by the supervisor
with credentials and policy in the environment. Serves storage verbs
(list_directory, about, copy_from_remote, etc.) to the app server over a
Unix Domain Socket.

The actual storage backend is whatever ``RCLONE_CONFIG_DEFAULT_TYPE`` selects
(currently ``iclouddrive``). rclone reads its own config from
``RCLONE_CONFIG_DEFAULT_*`` env vars the supervisor injects at spawn time, so
there's no config file on disk.
"""
