"""POM for the Settings page — Agent Profiles tab + Integrations tab + System tab."""

from __future__ import annotations

from playwright.sync_api import Locator, Page

from tests.e2e.pages.integrations_tab import IntegrationsTab


class ModelPickerLocator:
    """Interaction helper for the ModelPicker component."""

    def __init__(self, root: Locator):
        self._root = root
        self.input = root.locator("input[type='text']")

    def selected_value(self) -> str:
        return self.input.input_value()

    def open(self) -> None:
        self.input.focus()

    def items(self) -> Locator:
        return self._root.get_by_test_id("model-item")

    def select(self, model_name: str) -> None:
        self.open()
        self._root.locator(f"[data-model-name='{model_name}']").click()

    def select_different(self, current: str) -> str:
        """Open and pick the first model whose name differs from *current*."""
        self.open()
        items = self.items()
        items.first.wait_for(state="visible", timeout=10_000)
        for i in range(items.count()):
            name = items.nth(i).get_attribute("data-model-name")
            if name != current:
                items.nth(i).click()
                return name
        raise AssertionError("No alternative model found")


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
    def model_picker(self) -> ModelPickerLocator:
        return ModelPickerLocator(self.page.get_by_test_id("profile-model-picker"))

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

    def field(self, name: str) -> Locator:
        """Advanced inference field by name (e.g. 'temperature', 'top_k')."""
        return self.page.get_by_test_id(f"field-{name}")

    def auto_field(self, idx: int) -> Locator:
        """Inference fields with placeholder='auto' (temperature, top_k, top_p,
        repeat_penalty, context_window — in that source order)."""
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
        # ConfirmButton: first click arms ("Confirm?"), second click fires.
        self.page.get_by_role("button", name="Delete", exact=True).click()
        self.page.get_by_role("button", name="Confirm?").click()
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
    def vision_model_picker(self) -> ModelPickerLocator:
        return ModelPickerLocator(self.page.get_by_test_id("vision-model-picker"))

    @property
    def compaction_model_picker(self) -> ModelPickerLocator:
        return ModelPickerLocator(self.page.get_by_test_id("compaction-model-picker"))

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
        self.integrations = IntegrationsTab(page)

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

    def goto_integrations(self) -> "SettingsPage":
        """Open Settings and switch to the Integrations tab."""
        self.goto()
        self.page.get_by_role("button", name="Integrations").click()
        return self

    def close(self) -> "SettingsPage":
        """Toggle the Settings sidebar entry to leave the Settings view."""
        self.page.get_by_role("button", name="Settings", exact=True).click()
        return self
