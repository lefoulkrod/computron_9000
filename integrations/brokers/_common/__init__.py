"""Shared broker infrastructure: UDS RPC server, ready signal, exit codes.

Internal to the ``brokers`` package. Concrete brokers import directly from the
submodules (``integrations._rpc`` etc.), not from this package root — the
package has no external consumers and there's nothing to facade.
"""
