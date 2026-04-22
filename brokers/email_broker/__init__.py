"""Email broker: one process per email integration, speaks IMAP (read) and SMTP (send).

Launched as ``python -m brokers.email_broker`` by the supervisor with credentials
and policy in the environment. Serves domain verbs (search_messages,
fetch_message, send_message, …) to the app server over a Unix Domain Socket.
"""
