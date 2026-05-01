"""POM for the Integrations tab inside Settings + the Add modal wizard."""

from __future__ import annotations

from playwright.sync_api import Locator, Page


class AddIntegrationModal:
    """Multi-step wizard launched by the Add buttons.

    Step 1: provider picker — one card per catalog entry, each tagged
    ``provider-<slug>``.
    Step 2: explainer — has a ``Next`` button (testid ``wizard-next``).
    Step 3: credentials form — email + app password + Verify button.
    Step 4: verifying spinner / success page.
    """

    def __init__(self, page: Page):
        self.page = page

    @property
    def root(self) -> Locator:
        """The modal heading — anchors waits for "is the modal open?"."""
        return self.page.get_by_text("ADD INTEGRATION", exact=True)

    def pick_provider(self, slug: str) -> "AddIntegrationModal":
        """Click a provider card on step 1 and advance to the explainer."""
        self.page.get_by_test_id(f"provider-{slug}").click()
        return self

    def next_(self) -> "AddIntegrationModal":
        """Advance from the explainer to the credentials step."""
        self.page.get_by_test_id("wizard-next").click()
        return self

    @property
    def email_input(self) -> Locator:
        return self.page.get_by_test_id("wizard-email")

    @property
    def password_input(self) -> Locator:
        return self.page.get_by_test_id("wizard-password")

    @property
    def submit(self) -> Locator:
        """Verify & save button on the credentials step."""
        return self.page.get_by_test_id("wizard-submit")

    def cancel(self) -> None:
        """Close via the footer Cancel link."""
        self.page.get_by_role("button", name="Cancel").first.click()


class IntegrationsTab:
    """The Integrations tab inside Settings."""

    def __init__(self, page: Page):
        self.page = page
        self.add_modal = AddIntegrationModal(page)

    # ── Empty / unavailable states ───────────────────────────────────
    @property
    def empty_state_heading(self) -> Locator:
        """Heading shown when no integrations are registered."""
        return self.page.get_by_text("Connect your first integration")

    @property
    def empty_state_add(self) -> Locator:
        """The CTA in the empty state — opens the Add modal."""
        return self.page.get_by_test_id("integrations-add-first")

    @property
    def unavailable_heading(self) -> Locator:
        """Heading shown when the supervisor RPC is unreachable."""
        return self.page.get_by_text("Integrations unavailable")

    @property
    def retry_button(self) -> Locator:
        """The "Try again" button on the unavailable state."""
        return self.page.get_by_test_id("integrations-retry")

    # ── Add modal launch ─────────────────────────────────────────────
    def open_add_modal_from_empty(self) -> AddIntegrationModal:
        """Click the empty-state CTA to open the Add modal."""
        self.empty_state_add.click()
        self.add_modal.root.wait_for(state="visible")
        return self.add_modal

    def open_add_modal_from_list(self) -> AddIntegrationModal:
        """Click the in-list ADD button (only present when the list isn't empty)."""
        self.page.get_by_test_id("integrations-add-another").click()
        self.add_modal.root.wait_for(state="visible")
        return self.add_modal

    # ── List + detail (master-detail UI) ─────────────────────────────
    def row(self, integration_id: str) -> Locator:
        return self.page.get_by_test_id(f"integrations-row-{integration_id}")
