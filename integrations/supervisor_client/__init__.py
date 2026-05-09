"""Public client for calling supervisor verbs from app-server code.

Route handlers import ``call`` and ``SupervisorError`` from here (or from
``integrations``, which re-exports). Everything else in this sub-package
is internal.
"""

from integrations.supervisor_client._call import call
from integrations.supervisor_client._errors import SupervisorError

__all__ = [
    "SupervisorError",
    "call",
]
