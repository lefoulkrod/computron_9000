"""Shared fixtures for profile provider tests."""

import pytest
from playwright.sync_api import Page


def _first_model_for(page: Page, provider: str) -> str:
    """Look up an arbitrary model for the given provider (or empty string)."""
    res = page.request.get(f"/api/models?provider={provider}")
    if not res.ok:
        return ""
    models = res.json().get("models", [])
    return models[0]["name"] if models else ""


def _create_test_profile(
    page: Page, profile_id: str, provider: str, **overrides,
) -> None:
    """Create a test profile pinned to the given provider via the API."""
    model_name = overrides.pop("model", None) or _first_model_for(page, provider)
    data = {
        "id": profile_id,
        "name": f"Provider Test ({profile_id})",
        "description": "",
        "provider": provider,
        "model": model_name,
        "system_prompt": "",
        "skills": [],
        **overrides,
    }
    page.request.post("/api/profiles", data=data)


@pytest.fixture
def provider_profile(page: Page):
    """Factory fixture that creates a test profile pinned to a provider
    and cleans up after. Each profile carries its own provider — no global
    provider to flip.
    """
    created = []

    def _factory(profile_id: str, provider: str, **overrides):
        _create_test_profile(page, profile_id, provider, **overrides)
        created.append(profile_id)
        return profile_id

    yield _factory

    for pid in created:
        page.request.delete(f"/api/profiles/{pid}")
