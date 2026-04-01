"""Pytest configuration for test suite.

This file ensures that a local .env file is loaded before tests run so that
environment-variable-driven configuration works consistently in tests.
It also redirects conversation persistence to a temp directory so tests
never write to the real ~/.computron_9000/conversations/ location.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def _load_env_for_tests() -> None:
    """Automatically load .env at the start of the test session."""
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
        logger.info("Loaded environment from %s for tests", env_path)
    else:
        logger.info("No .env file found at %s; relying on process environment", env_path)


@pytest.fixture(autouse=True)
def _isolate_conversations(tmp_path: Path) -> None:
    """Redirect all conversation persistence to a temp directory.

    Prevents tests from reading or writing the real conversations store.
    """
    with patch(
        "conversations._store._get_conversations_dir",
        return_value=tmp_path / "conversations",
    ):
        yield
