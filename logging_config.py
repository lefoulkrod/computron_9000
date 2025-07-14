"""Utility functions for configuring application logging."""

import logging
import sys


def setup_logging() -> None:
    """Configure basic loggers for the application.

    Sets the root logger to output to ``stdout`` and adjusts log levels for
    specific third‑party libraries and application modules.
    """

    logging.basicConfig(level=logging.WARN, stream=sys.stdout)
    logging.getLogger("tools").setLevel(logging.WARNING)
    logging.getLogger("ollama").setLevel(logging.WARNING)
    logging.getLogger("agents.ollama").setLevel(logging.WARNING)
    logging.getLogger("agents.ollama.deep_research").setLevel(logging.DEBUG)
