"""Shared fixtures for e2e tests."""

import os

import pytest

BASE_URL = os.environ.get("COMPUTRON_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure the browser context for all e2e tests."""
    return {"base_url": BASE_URL}


@pytest.fixture(scope="session")
def wizard_choices():
    """Stores the model names picked during the setup wizard."""
    return {}


def _find_cloud_model_card(page, name_fragment):
    """Find a model card whose name contains *name_fragment* and has a 'cloud' badge.

    Returns the first matching card locator, or falls back to the first
    card if no cloud variant is found.
    """
    cards = page.locator("[class*='modelCard']")
    cards.first.wait_for(state="visible", timeout=15_000)
    count = cards.count()
    for i in range(count):
        card = cards.nth(i)
        name = card.locator("[class*='modelName']").text_content().lower()
        has_cloud = card.locator("[class*='badgeCloud']").count() > 0
        if name_fragment.lower() in name and has_cloud:
            return card
    # Fallback — first card
    return cards.first


@pytest.fixture(scope="session", autouse=True)
def _complete_setup_wizard(browser, wizard_choices):
    """Run the setup wizard once before all tests.

    Checks the API to determine if setup is needed, then drives the
    wizard UI. Selects kimi (cloud) as main model and qwen3.5 (cloud)
    as vision model. Stores the picked model names in wizard_choices so
    tests can verify persistence.
    """
    context = browser.new_context(base_url=BASE_URL)
    page = context.new_page()

    # Check the API to determine if setup is needed — avoids DOM race conditions
    settings = page.request.get("/api/settings").json()
    if settings.get("setup_complete"):
        page.close()
        context.close()
        return

    page.goto("/")

    # Wait for the wizard to render
    page.get_by_text("Welcome to Computron").wait_for(state="visible", timeout=10_000)
    page.get_by_role("button", name="Get Started").click()

    # Main model — pick kimi cloud variant
    page.get_by_text("Choose your main model").wait_for(state="visible")
    main_card = _find_cloud_model_card(page, "kimi")
    wizard_choices["main_model"] = main_card.locator("[class*='modelName']").text_content()
    main_card.click()
    page.get_by_role("button", name="Continue").click()

    # Vision model — pick qwen3.5 cloud variant
    page.get_by_text("Choose a vision model").wait_for(state="visible")
    vision_card = _find_cloud_model_card(page, "qwen3.5")
    wizard_choices["vision_model"] = vision_card.locator("[class*='modelName']").text_content()
    vision_card.click()
    page.get_by_role("button", name="Continue").click()

    # Finish
    page.get_by_text("You're all set").wait_for(state="visible")
    page.get_by_role("button", name="Start Chatting").click()
    page.get_by_text("Welcome to Computron").wait_for(state="hidden")

    # Wait for settings to persist before closing — the wizard's async
    # save can still be in-flight when the UI dismisses
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
