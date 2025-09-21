"""Utility functions for configuring application logging."""

import logging
import sys


def setup_logging() -> None:
    """Configure basic loggers for the application.

    Sets the root logger to output to ``stdout`` and adjusts log levels for
    specific third-party libraries and application modules.
    """
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout)
    # Default 'tools' namespace to WARNING so normal runs are not overly verbose.
    # Individual tools can raise their own logger levels when deeper diagnostics are needed.
    logging.getLogger("tools").setLevel(logging.WARNING)
    logging.getLogger("tools.virtual_computer").setLevel(logging.INFO)
    logging.getLogger("ollama").setLevel(logging.WARNING)
    logging.getLogger("agents.ollama").setLevel(logging.DEBUG)
    logging.getLogger("agents.ollama.deep_researchV2").setLevel(logging.DEBUG)
    # REPLs default to INFO so users see helpful output without increasing
    # global verbosity. Individual REPL modules can still override as needed.
    logging.getLogger("repls").setLevel(logging.INFO)
