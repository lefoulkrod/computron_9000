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


def _find_cloud_model_card(page, name_fragment):
    """Find a model card whose name contains *name_fragment* and has a
    'cloud' badge. Falls back to the first card if no match."""
    cards = page.locator("[class*='modelCard']")
    cards.first.wait_for(state="visible", timeout=15_000)
    count = cards.count()
    for i in range(count):
        card = cards.nth(i)
        name = card.locator("[class*='modelName']").text_content().lower()
        has_cloud = card.locator("[class*='badgeCloud']").count() > 0
        if name_fragment.lower() in name and has_cloud:
            return card
    return cards.first


@pytest.fixture(scope="session", autouse=True)
def _complete_setup_wizard(browser, wizard_choices):
    """Drive the setup wizard once before any test runs.

    Picks kimi (cloud) as main model and qwen3.5 (cloud) as vision model.
    Records the chosen names in wizard_choices so post-condition tests
    can verify persistence.
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

    page.get_by_text("Welcome to Computron").wait_for(state="visible", timeout=10_000)
    page.get_by_role("button", name="Get Started").click()

    page.get_by_text("Choose your main model").wait_for(state="visible")
    main_card = _find_cloud_model_card(page, "kimi")
    wizard_choices["main_model"] = main_card.locator("[class*='modelName']").text_content()
    main_card.click()
    page.get_by_role("button", name="Continue").click()

    page.get_by_text("Choose a vision model").wait_for(state="visible")
    vision_card = _find_cloud_model_card(page, "qwen3.5")
    wizard_choices["vision_model"] = vision_card.locator("[class*='modelName']").text_content()
    vision_card.click()
    page.get_by_role("button", name="Continue").click()

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
