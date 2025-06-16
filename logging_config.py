"""Utility functions for configuring application logging."""

import logging
import sys

def setup_logging() -> None:
    """Configure basic loggers for the application.

    Sets the root logger to output to ``stdout`` and adjusts log levels for
    specific third‑party libraries.
    """

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.DEBUG)
