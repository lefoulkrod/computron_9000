"""Integrations subsystem facade.

Public API surface for the rest of the app. Implementation (supervisor,
brokers, shared RPC framing, vault storage) lives in sibling sub-packages
that aren't re-exported here — they're the subsystem's internals.

External consumers (tool handlers, app-server routes) talk to integrations
through the ``broker_client`` submodule::

    from integrations import broker_client

    result = await broker_client.call(
        "gmail_personal", "list_mailboxes", {}, app_sock_path=...,
    )

    try:
        ...
    except broker_client.IntegrationAuthFailed:
        ...

Keeping the submodule visible (rather than flattening individual symbols)
gives external code one clear namespace per surface and matches the
``requests.get`` / ``asyncio.sleep`` convention.

Internal modules inside this package continue to import from their defining
submodule, not through this facade.
"""

from integrations import broker_client

__all__ = ["broker_client"]
