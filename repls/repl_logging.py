"""Shared logging helpers for REPL scripts.

By default REPL loggers propagate to the root logger so application-wide
handlers configured via :func:`logging_config.setup_logging` are used. This
makes other application loggers visible in REPL sessions by default. If a
REPL prefers an isolated handler (no propagation) callers can request that
behavior via ``propagate=False``.
"""

from __future__ import annotations

import logging
import sys
from typing import Final

_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def get_repl_logger(
    module_stub: str,
    *,
    level: int = logging.DEBUG,
    propagate: bool = True,
) -> logging.Logger:
    """Return a logger for a REPL file with stable namespace.

    Args:
        module_stub: Short identifier for the REPL script (e.g. "workflow").
        level: Logging level to set for the REPL logger (default DEBUG for verbose diagnostics).
        propagate: If True (default), allow records to bubble to the root logger so
            that application-wide handlers (configured in ``logging_config.setup_logging``)
            emit other namespaces alongside REPL output. When False, a dedicated
            handler is attached and propagation suppressed to avoid duplicate
            messages.

    Returns:
        Configured logger instance.
    """
    name = f"repls.{module_stub}" if module_stub else "repls"
    logger = logging.getLogger(name)
    if not logger.handlers and not propagate:
        # Only attach a dedicated handler when not propagating; otherwise rely on root handlers
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = propagate
    return logger
