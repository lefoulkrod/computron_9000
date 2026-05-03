"""E2E tests for the Integrations tab UI.

We don't commit real credentials, so the happy-path "Add → connected"
flow isn't covered here. What we do cover end-to-end:

- Empty state on a fresh container.
- Add modal lifecycle (open, navigate to credentials step, validate
  empty-form submit gating, cancel).
- Unavailable state (chmod the supervisor's app.sock so the route
  hits PermissionError → UI surfaces the "Integrations unavailable"
  empty state with a Retry button).

Manual testing covers the AUTH / UPSTREAM / connected paths against
real providers; that's documented in the integrations plan.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from e2e._helpers import container_run_root
from e2e.pages import SettingsPage


def test_empty_state_shows_when_no_integrations(page: Page) -> None:
    """Fresh container has no integrations registered → the empty state
    invites the user to connect their first one with a single CTA."""
    settings = SettingsPage(page).goto_integrations()
    expect(settings.integrations.empty_state_heading).to_be_visible()
    expect(settings.integrations.empty_state_add).to_be_visible()


def test_add_modal_opens_from_empty_state(page: Page) -> None:
    """Clicking the empty-state CTA opens the Add modal at step 1
    (provider picker)."""
    settings = SettingsPage(page).goto_integrations()
    modal = settings.integrations.open_add_modal_from_empty()

    expect(modal.root).to_be_visible()
    # Step 1 shows both supported providers as picker cards.
    expect(page.get_by_test_id("provider-icloud")).to_be_visible()
    expect(page.get_by_test_id("provider-gmail")).to_be_visible()


def test_add_modal_cancel_closes_it(page: Page) -> None:
    """The footer Cancel button on the provider picker closes the modal."""
    settings = SettingsPage(page).goto_integrations()
    modal = settings.integrations.open_add_modal_from_empty()
    modal.cancel()
    expect(modal.root).to_be_hidden()


def test_picking_provider_advances_to_explainer_step(page: Page) -> None:
    """Clicking a provider card moves the wizard to step 2 — the
    explainer that names the vendor (e.g. "Connect iCloud")."""
    settings = SettingsPage(page).goto_integrations()
    modal = settings.integrations.open_add_modal_from_empty()
    modal.pick_provider("icloud")
    expect(page.get_by_text("Connect iCloud")).to_be_visible()


def test_credentials_step_disables_submit_when_form_empty(page: Page) -> None:
    """On step 3 the Verify & save button stays disabled until both the
    email and the app password are filled in. Prevents an obviously-bad
    submit from hitting the supervisor."""
    settings = SettingsPage(page).goto_integrations()
    modal = settings.integrations.open_add_modal_from_empty()
    modal.pick_provider("icloud").next_()

    # Fields are empty by default → submit must be disabled.
    expect(modal.email_input).to_have_value("")
    expect(modal.password_input).to_have_value("")
    expect(modal.submit).to_be_disabled()

    # Filling only the email isn't enough — password is also required.
    modal.email_input.fill("test@icloud.com")
    expect(modal.submit).to_be_disabled()

    # Add the password and submit becomes enabled.
    modal.password_input.fill("xxxx-xxxx-xxxx-xxxx")
    expect(modal.submit).to_be_enabled()


def test_unavailable_state_when_supervisor_socket_blocked(page: Page) -> None:
    """When the route handler can't connect to the supervisor's
    ``app.sock`` (e.g. supervisor crashed mid-call, broker user perms
    misconfigured), the UI shows the dedicated "Integrations
    unavailable" empty state with a Try again button — distinct from
    the generic load-error Callout used for other failures.

    We engineer the failure by chmod'ing the socket so the aiohttp app
    (running as ``computron``) can't connect; the supervisor (running
    as ``broker``) keeps listening. Restoring the mode + clicking
    Retry brings the list back without a page reload.
    """
    container_run_root("chmod 600 /run/cvault/app.sock")
    try:
        settings = SettingsPage(page).goto_integrations()
        expect(settings.integrations.unavailable_heading).to_be_visible()
        expect(settings.integrations.retry_button).to_be_visible()
    finally:
        # Restore mode unconditionally so other tests (and a failed test
        # mid-block) don't leave the socket inaccessible to the app.
        container_run_root("chmod 660 /run/cvault/app.sock")

    settings.integrations.retry_button.click()
    expect(settings.integrations.unavailable_heading).to_be_hidden()
    # No integrations are registered → the empty state should now show.
    expect(settings.integrations.empty_state_heading).to_be_visible()
