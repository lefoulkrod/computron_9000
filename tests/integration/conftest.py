"""Integration test fixtures.

These tests require a running container with Ollama available.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _require_running_container():
    """Skip integration tests unless COMPUTRON_URL is set."""
    if not os.environ.get("COMPUTRON_URL"):
        pytest.skip("COMPUTRON_URL not set — integration tests need a running container")
