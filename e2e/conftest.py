"""Root conftest for the e2e suite.

Keeps only what pytest needs to discover here. Generic infrastructure
helpers live in `e2e/_helpers.py`; the wizard auto-setup lives in
`e2e/_setup.py` and is registered via the pytest_plugins hook below.
"""

import os

import pytest

BASE_URL = os.environ.get("COMPUTRON_URL", "http://localhost:8080")

# Auto-completes the setup wizard before any test runs. Lives in a
# sibling module so the autouse fixture's implementation isn't crammed
# into the root conftest.
pytest_plugins = ["e2e._setup"]


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure the browser context for all e2e tests."""
    return {"base_url": BASE_URL}
