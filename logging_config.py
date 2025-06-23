"""Utility functions for configuring application logging."""

import logging
import sys

def setup_logging() -> None:
    """Configure basic loggers for the application.

    Sets the root logger to output to ``stdout`` and adjusts log levels for
    specific third‑party libraries and application modules.
    """

    logging.basicConfig(level=logging.WARN, stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("agents.pydantic_ai").setLevel(logging.DEBUG)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logging.getLogger("tools").setLevel(logging.DEBUG)
    logging.getLogger("agents.adk").setLevel(logging.DEBUG)
    logging.getLogger("google.adk").setLevel(logging.DEBUG)