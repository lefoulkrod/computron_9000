"""Auto-completes the setup wizard before the e2e suite runs.

Registered as a pytest plugin from the root conftest. The autouse session
fixture runs once and drives the wizard UI so the rest of the suite has
a usable app to test against.

The suite is expected to run on a fresh container (via `just e2e`). If
the container already has setup_complete=true, the fixture fails the
session loudly — silently no-op'ing would let wizard post-condition
tests pass without actually exercising the wizard.
"""

import os

import pytest

BASE_URL = os.environ.get("COMPUTRON_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def wizard_choices():
    """Records the model names picked by the wizard so tests can assert
    they were persisted correctly."""
    return {}


def _pick_model(page, name_fragment):
    """Find and click a model in the ModelPicker whose name contains
    *name_fragment*. Returns the full model name."""
    items = page.get_by_test_id("model-item")
    items.first.wait_for(state="visible", timeout=15_000)
    count = items.count()
    for i in range(count):
        item = items.nth(i)
        name = item.get_attribute("data-model-name")
        if name and name_fragment.lower() in name.lower():
            item.click()
            return name
    # Fallback: pick the first item
    name = items.first.get_attribute("data-model-name")
    items.first.click()
    return name


@pytest.fixture(scope="session", autouse=True)
def _complete_setup_wizard(browser, wizard_choices):
    """Drive the setup wizard once before any test runs.

    Picks Ollama as provider, kimi (cloud) as main model and qwen3.5
    (cloud) as vision model. Records the chosen names in wizard_choices
    so post-condition tests can verify persistence.
    """
    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()

    settings = page.request.get("/api/settings").json()
    if settings.get("setup_complete"):
        page.close()
        context.close()
        pytest.fail(
            "e2e suite requires a fresh container — setup_complete is already true. "
            "Run via `just e2e` (spawns a throwaway container with empty state) "
            "instead of pointing at an already-initialized container."
        )

    page.goto("/")

    # Step 0: Welcome
    page.get_by_text("Welcome to Computron").wait_for(state="visible", timeout=10_000)
    page.get_by_role("button", name="Get Started").click()

    # Step 1: Provider — pick Ollama with localhost URL (network=host)
    page.get_by_text("Choose your LLM provider").wait_for(state="visible")
    page.get_by_text("Ollama (local)").click()
    page.locator("#ollama-url").fill("http://localhost:11434")
    page.get_by_role("button", name="Connect").click()

    # Step 2: Main Model
    page.get_by_role("heading", name="Choose your main model").wait_for(state="visible", timeout=15_000)
    wizard_choices["main_model"] = _pick_model(page, "kimi-k2.5")
    page.get_by_role("button", name="Continue").click()

    # Step 3: Vision Model. The picker's placeholder repeats the heading
    # text, so match by role to keep the locator unambiguous.
    page.get_by_role("heading", name="Choose a vision model").wait_for(state="visible")
    wizard_choices["vision_model"] = _pick_model(page, "qwen3.5:cloud")
    page.get_by_role("button", name="Continue").click()

    # Step 4: Ready
    page.get_by_text("You're all set").wait_for(state="visible")
    page.get_by_role("button", name="Start Chatting").click()
    page.get_by_text("Welcome to Computron").wait_for(state="hidden")

    # Wait for settings to persist before closing — the wizard's async
    # save can still be in-flight when the UI dismisses.
    page.wait_for_function(
        """async () => {
            const r = await fetch('/api/settings');
            const s = await r.json();
            return s.setup_complete === true;
        }""",
        timeout=10_000,
    )

    page.close()
    context.close()
