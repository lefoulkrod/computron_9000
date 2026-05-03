"""Exception hierarchy raised by ``broker_client.call``.

The base ``IntegrationError`` catches every failure mode. Two subclasses give
callers a place to branch on the reasons they most commonly need to react to
differently:

- ``IntegrationAuthFailed`` — the broker told us the upstream rejected our
  credentials. The user needs to reconnect the integration.
- ``IntegrationWriteDenied`` — the broker refused a write-classified verb
  because the integration's ``write_allowed`` flag is false. The user needs
  to enable writes.

Other broker error codes (``NETWORK`` / ``UPSTREAM`` / ``BAD_REQUEST``) land
on the base ``IntegrationError`` for now. Promote them to dedicated subclasses
when a real caller wants to catch one specifically.
"""

from __future__ import annotations


class IntegrationError(Exception):
    """Base for every failure ``broker_client.call`` can raise."""


class IntegrationNotConnected(IntegrationError):
    """The supervisor doesn't know about this integration.

    Either the ``integration_id`` has never been added, or it was removed
    after the caller last listed integrations.
    """


class IntegrationAuthFailed(IntegrationError):
    """The broker reported upstream authentication failure.

    The integration is effectively disabled until the user reconnects it. The
    broker process may have exited; the supervisor's state machine handles
    transitioning to ``auth_failed``.
    """


class IntegrationWriteDenied(IntegrationError):
    """The broker refused a write-classified verb.

    Fires when the integration's ``write_allowed`` flag is false. Tool handlers
    should surface this with a hint that the user can enable writes in
    Settings → Integrations.
    """
