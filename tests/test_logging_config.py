"""Unit tests for global logging configuration.

These tests assert that calling `setup_logging` configures key logger levels
used throughout the application, including the REPL namespace.
"""

import logging

import pytest

from logging_config import setup_logging


@pytest.mark.unit
def test_setup_logging_sets_expected_levels() -> None:
    """Ensure calling setup_logging applies expected logger levels.

    The REPL namespace should default to INFO so interactive output is visible.
    Some agent namespaces are more verbose for debugging tool flows.
    """
    # Act
    setup_logging()

    # Assert specific namespaces of interest
    assert logging.getLogger("repls").getEffectiveLevel() == logging.INFO
    assert logging.getLogger("tools").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("ollama").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("agents.ollama").getEffectiveLevel() == logging.DEBUG
