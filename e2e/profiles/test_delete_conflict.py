"""E2E tests for the delete-blocked-by-goal conflict Callout."""

import pytest
from playwright.sync_api import Page, expect

from e2e._helpers import container_exec
from e2e.pages import SettingsPage


@pytest.fixture
def blocking_goal(page: Page):
    """Create a profile + a goal whose task references it.

    Yields a dict with the IDs and the goal description so tests can
    assert on the conflict Callout content. Tears down both on exit so
    profiles list stays clean across tests.
    """
    profile_id = "test_pinned_target"
    goal_description = "E2E delete-conflict test goal"

    page.request.post("/api/profiles", data={
        "id": profile_id,
        "name": "Pinned Target",
        "description": "test profile pinned by a goal",
        "model": "",
        "skills": [],
    })

    # Goals have no HTTP create endpoint — seed via the running app's
    # tasks store. File-backed, so the next API read sees it.
    goal_id = container_exec(
        "from tasks import get_store\n"
        "s = get_store()\n"
        f"g = s.create_goal({goal_description!r})\n"
        f"s.create_task(g.id, 'blocking task', 'noop', agent_profile={profile_id!r})\n"
        "print(g.id)\n"
    )

    yield {
        "profile_id": profile_id,
        "goal_id": goal_id,
        "goal_description": goal_description,
    }

    # Goal first — so the profile is no longer pinned and the delete succeeds
    page.request.delete(f"/api/goals/{goal_id}")
    page.request.delete(f"/api/profiles/{profile_id}")


def test_delete_blocked_shows_conflict_callout(page: Page, blocking_goal):
    """Clicking Delete on a profile pinned by a goal shows the Callout
    listing the blocking goal and leaves the profile in the list."""
    settings = SettingsPage(page).goto()
    settings.profiles.select(blocking_goal["profile_id"])
    settings.builder.delete()

    expect(settings.builder.delete_conflict).to_be_visible()
    expect(settings.builder.delete_conflict).to_contain_text("Can't delete")
    expect(settings.builder.delete_conflict).to_contain_text(blocking_goal["goal_description"])

    # Profile must still be in the list — the delete was rejected
    expect(settings.profiles.item(blocking_goal["profile_id"])).to_be_visible()


def test_dismiss_conflict_callout(page: Page, blocking_goal):
    """Clicking the × on the Callout removes it without affecting state."""
    settings = SettingsPage(page).goto()
    settings.profiles.select(blocking_goal["profile_id"])
    settings.builder.delete()
    expect(settings.builder.delete_conflict).to_be_visible()

    settings.builder.dismiss_delete_conflict()
    expect(settings.builder.delete_conflict).to_be_hidden()


def test_switching_profiles_clears_conflict(page: Page, blocking_goal):
    """Picking a different profile clears any stale conflict Callout."""
    settings = SettingsPage(page).goto()
    settings.profiles.select(blocking_goal["profile_id"])
    settings.builder.delete()
    expect(settings.builder.delete_conflict).to_be_visible()

    # Switch to Computron (always present — it's the default)
    settings.profiles.select("computron")
    expect(settings.builder.delete_conflict).to_be_hidden()
