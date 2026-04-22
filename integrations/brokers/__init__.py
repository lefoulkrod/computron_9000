"""Brokers: long-lived subprocesses that speak upstream protocols on behalf of integrations.

Each concrete broker lives in its own sub-package (``email_broker``, ``calendar_broker``,
``mcp_broker``) and is launched as ``python -m integrations.brokers.<name>``. Shared infrastructure
(UDS RPC server, ready-signal helper, exit-code constants) is in ``integrations.brokers._common``.
"""
