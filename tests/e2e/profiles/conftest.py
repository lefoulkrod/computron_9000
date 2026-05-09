"""Shared fixtures for profile provider tests."""

import pytest
from playwright.sync_api import Page


def _set_provider(page: Page, provider: str) -> None:
    """Switch the app's LLM provider via the settings API."""
    page.request.put("/api/settings", data={"llm_provider": provider})


def _create_test_profile(page: Page, profile_id: str, **overrides) -> None:
    """Create a test profile via the API."""
    models = page.request.get("/api/models").json().get("models", [])
    model_name = models[0]["name"] if models else ""
    data = {
        "id": profile_id,
        "name": f"Provider Test ({profile_id})",
        "description": "",
        "model": model_name,
        "system_prompt": "",
        "skills": [],
        **overrides,
    }
    page.request.post("/api/profiles", data=data)


@pytest.fixture
def provider_profile(page: Page):
    """Factory fixture that creates a test profile and cleans up after."""
    created = []

    def _factory(profile_id: str, provider: str, **overrides):
        _set_provider(page, provider)
        _create_test_profile(page, profile_id, **overrides)
        created.append(profile_id)
        return profile_id

    yield _factory

    for pid in created:
        page.request.delete(f"/api/profiles/{pid}")
    _set_provider(page, "ollama")
