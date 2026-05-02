"""Rclone broker: one process per rclone storage integration.

Launched as ``python -m integrations.brokers.rclone_broker`` by the supervisor
with credentials and policy in the environment. Serves storage verbs
(list_directory, about, copy_from_remote, etc.) to the app server over a
Unix Domain Socket.
"""
