"""Shared logging helpers for REPL scripts.

All REPL loggers emit at DEBUG level regardless of the root logger so that
interactive diagnostics are always visible. Other packages still respect
their configured levels because REPL loggers are non-propagating and have
their own handler.
"""

from __future__ import annotations

import logging
import sys
from typing import Final

_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def get_repl_logger(module_stub: str) -> logging.Logger:
    """Return a logger for a REPL file with stable namespace.

    Args:
        module_stub: Short identifier for the REPL script (e.g. "workflow").

    Returns:
        Configured logger instance.
    """
    level = logging.DEBUG
    name = f"repls.{module_stub}" if module_stub else "repls"
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)
        # Avoid double emission via root
        logger.propagate = False
    # Ensure at least requested level
    logger.setLevel(level)
    return logger
