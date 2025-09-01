"""Utility functions for configuring application logging."""

import logging
import sys


def setup_logging() -> None:
    """Configure basic loggers for the application.

    Sets the root logger to output to ``stdout`` and adjusts log levels for
    specific third‑party libraries and application modules.
    """
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout)
    logging.getLogger("tools").setLevel(logging.WARNING)
    logging.getLogger("tools.virtual_computer").setLevel(logging.INFO)
    logging.getLogger("ollama").setLevel(logging.WARNING)
    logging.getLogger("agents.ollama").setLevel(logging.DEBUG)
    logging.getLogger("agents.ollama.deep_researchV2").setLevel(logging.DEBUG)
