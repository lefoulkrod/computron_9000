"""POM for the Settings page — Agent Profiles tab + System tab."""

from __future__ import annotations

from playwright.sync_api import Locator, Page


class ProfileList:
    """Left-hand pane of the Agent Profiles tab — the list of profiles."""

    def __init__(self, page: Page):
        self.page = page

    def item(self, profile_id: str) -> Locator:
        """The clickable list row for a profile."""
        return self.page.locator(f"[data-testid='profile-item-{profile_id}']")

    def select(self, profile_id: str) -> None:
        """Click a profile and wait for the builder pane to populate."""
        self.item(profile_id).click()
        self.page.locator("input[placeholder='Profile name']").wait_for(state="visible")

    def new(self) -> None:
        """Click '+ New' and wait for the empty builder to render."""
        self.page.get_by_role("button", name="+ New").click()
        self.page.locator("input[placeholder='Profile name']").wait_for(state="visible")


class ProfileBuilder:
    """Right-hand pane of the Agent Profiles tab — edit/save/delete the
    selected profile."""

    def __init__(self, page: Page):
        self.page = page

    # ── Inputs ────────────────────────────────────────────────────
    @property
    def name_input(self) -> Locator:
        return self.page.locator("input[placeholder='Profile name']")

    @property
    def description_input(self) -> Locator:
        return self.page.locator("input[placeholder='Short description']")

    @property
    def system_prompt(self) -> Locator:
        return self.page.locator("textarea[placeholder='System prompt...']")

    @property
    def model_select(self) -> Locator:
        return self.page.locator("select").first

    @property
    def enabled_toggle(self) -> Locator:
        return self.page.locator("[data-testid='profile-enabled-toggle'] input[type='checkbox']")

    @property
    def skill_chips(self) -> Locator:
        return self.page.locator("button[class*='chip']")

    def preset(self, label: str) -> Locator:
        return self.page.locator("[class*='presetBtn']", has_text=label)

    # ── Advanced section ──────────────────────────────────────────
    def open_advanced(self) -> "ProfileBuilder":
        self.page.get_by_text("Advanced Settings").click()
        return self

    def auto_field(self, idx: int) -> Locator:
        """Inference fields with placeholder='auto' (temperature, top_k, top_p,
        repeat_penalty, num_ctx — in that source order)."""
        return self.page.locator("input[placeholder='auto']").nth(idx)

    def unlimited_field(self, idx: int) -> Locator:
        """Fields with placeholder='unlimited' (num_predict, max_iterations)."""
        return self.page.locator("input[placeholder='unlimited']").nth(idx)

    @property
    def thinking_switch(self) -> Locator:
        return self.page.get_by_role("switch", name="Thinking")

    # ── Action bar ────────────────────────────────────────────────
    def save(self) -> "ProfileBuilder":
        self.page.get_by_role("button", name="Save").click()
        return self

    def revert(self) -> "ProfileBuilder":
        self.page.get_by_role("button", name="Revert").click()
        return self

    def duplicate(self) -> "ProfileBuilder":
        self.page.get_by_role("button", name="Duplicate").click()
        return self

    def delete(self) -> "ProfileBuilder":
        # exact=True so a profile NAMED "Delete X" doesn't collide with the button
        self.page.get_by_role("button", name="Delete", exact=True).click()
        return self

    # ── Inline feedback ───────────────────────────────────────────
    @property
    def save_error(self) -> Locator:
        return self.page.locator("[data-testid='profile-save-error']")

    @property
    def delete_conflict(self) -> Locator:
        return self.page.locator("[data-testid='profile-delete-conflict']")

    def dismiss_delete_conflict(self) -> "ProfileBuilder":
        self.delete_conflict.get_by_role("button", name="Dismiss").click()
        return self


class SystemTab:
    """The System tab inside Settings."""

    def __init__(self, page: Page):
        self.page = page

    @property
    def default_agent_select(self) -> Locator:
        return self.page.locator("select").first

    @property
    def vision_model_select(self) -> Locator:
        return self.page.locator("select").nth(1)

    @property
    def compaction_model_select(self) -> Locator:
        return self.page.locator("select").nth(2)

    def open_vision_advanced(self) -> "SystemTab":
        self.page.get_by_test_id("vision-advanced-toggle").click()
        self.page.get_by_test_id("vision-advanced-panel").wait_for(state="visible")
        return self

    @property
    def vision_think_toggle(self) -> Locator:
        return self.page.get_by_test_id("vision-think-toggle")

    def vision_option(self, key: str) -> Locator:
        return self.page.get_by_test_id(f"vision-option-{key}")


class SettingsPage:
    """Settings page — sidebar entry + Agent Profiles / System tabs."""

    def __init__(self, page: Page):
        self.page = page
        self.profiles = ProfileList(page)
        self.builder = ProfileBuilder(page)
        self.system = SystemTab(page)

    def goto(self) -> "SettingsPage":
        """Open Settings on the Agent Profiles tab (default)."""
        self.page.goto("/")
        self.page.get_by_role("button", name="Settings", exact=True).click()
        self.page.get_by_role("button", name="Agent Profiles").wait_for(state="visible")
        return self

    def goto_system(self) -> "SettingsPage":
        """Open Settings and switch to the System tab."""
        self.goto()
        self.page.get_by_role("button", name="System").click()
        self.page.locator("[class*='settingRow']").first.wait_for(state="visible")
        return self

    def close(self) -> "SettingsPage":
        """Toggle the Settings sidebar entry to leave the Settings view."""
        self.page.get_by_role("button", name="Settings", exact=True).click()
        return self
