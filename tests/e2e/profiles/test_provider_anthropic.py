"""E2E tests: Anthropic provider field visibility and presets."""

import re

from playwright.sync_api import expect

from tests.e2e.pages import SettingsPage


VISIBLE_FIELDS = ("temperature", "top_k", "top_p", "num_predict", "max_iterations", "think")
HIDDEN_FIELDS = ("repeat_penalty", "num_ctx")


def test_anthropic_field_visibility(page, provider_profile):
    """Anthropic shows top_k but hides repeat_penalty and num_ctx."""
    provider_profile("test_prov_anth_vis", "anthropic")

    settings = SettingsPage(page).goto()
    settings.profiles.select("test_prov_anth_vis")
    settings.builder.open_advanced()

    for name in VISIBLE_FIELDS:
        expect(settings.builder.field(name)).to_be_visible()
    for name in HIDDEN_FIELDS:
        expect(settings.builder.field(name)).not_to_be_attached()


def test_anthropic_code_preset(page, provider_profile):
    """Code preset on Anthropic sets temperature=1.0 and think=true."""
    provider_profile("test_prov_anth_code", "anthropic", temperature=1.0, think=True)

    settings = SettingsPage(page).goto()
    settings.profiles.select("test_prov_anth_code")

    expect(settings.builder.preset("Code")).to_have_class(re.compile(r"presetActive"))


def test_anthropic_thinking_budget_with_think(page, provider_profile):
    """Thinking budget dropdown appears when thinking is enabled."""
    provider_profile("test_prov_anth_budget", "anthropic", think=True)

    settings = SettingsPage(page).goto()
    settings.profiles.select("test_prov_anth_budget")
    settings.builder.open_advanced()

    expect(settings.builder.field("thinking_budget")).to_be_visible()
    expect(settings.builder.field("reasoning_effort")).not_to_be_attached()
    expect(settings.builder.field("reasoning_summary")).not_to_be_attached()


def test_anthropic_max_output_placeholder(page, provider_profile):
    """Max Output field shows '16384' placeholder on Anthropic."""
    provider_profile("test_prov_anth_placeholder", "anthropic")

    settings = SettingsPage(page).goto()
    settings.profiles.select("test_prov_anth_placeholder")
    settings.builder.open_advanced()

    expect(settings.builder.field("num_predict")).to_have_attribute("placeholder", "16384")
