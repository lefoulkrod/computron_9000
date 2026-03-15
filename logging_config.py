"""Utility functions for configuring application logging."""

import logging

from rich.logging import RichHandler


def setup_logging() -> None:
    """Configure loggers with rich console output.

    Sets the root logger to use Rich for colored, formatted console output
    and adjusts log levels for specific libraries and application modules.
    """
    handler = RichHandler(
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        show_time=True,
        show_path=True,
        markup=True,
    )
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
    )
    # Default 'tools' namespace to WARNING so normal runs are not overly verbose.
    # Individual tools can raise their own logger levels when deeper diagnostics are needed.
    logging.getLogger("tools").setLevel(logging.WARNING)
    logging.getLogger("tools.virtual_computer").setLevel(logging.INFO)
    logging.getLogger("tools.browser").setLevel(logging.DEBUG)
    logging.getLogger("tools.desktop").setLevel(logging.DEBUG)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("ollama").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("agents").setLevel(logging.DEBUG)
    logging.getLogger("sdk").setLevel(logging.DEBUG)
    # REPLs default to INFO so users see helpful output without increasing
    # global verbosity. Individual REPL modules can still override as needed.
    logging.getLogger("repls").setLevel(logging.INFO)
