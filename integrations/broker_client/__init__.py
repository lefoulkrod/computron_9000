"""Public client for calling broker verbs from app-server code.

Tool handlers import ``call`` from here (or from ``integrations``, which
re-exports). Everything in this sub-package except the symbols listed below
is internal and shouldn't be imported from outside.
"""

from integrations.broker_client._call import call
from integrations.broker_client._errors import (
    IntegrationAuthFailed,
    IntegrationError,
    IntegrationNotConnected,
    IntegrationWriteDenied,
)

__all__ = [
    "IntegrationAuthFailed",
    "IntegrationError",
    "IntegrationNotConnected",
    "IntegrationWriteDenied",
    "call",
]
