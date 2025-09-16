"""Pytest configuration for test suite.

This file ensures that a local .env file is loaded before tests run so that
environment-variable-driven configuration works consistently in tests.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def _load_env_for_tests() -> None:
    """Automatically load .env at the start of the test session.

    This matches the app behavior (config.load_config calls load_dotenv at import).
    We do it here explicitly for clarity and to support tests that read env before
    importing the app config module.
    """
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
        logger.info("Loaded environment from %s for tests", env_path)
    else:
        logger.info("No .env file found at %s; relying on process environment", env_path)
