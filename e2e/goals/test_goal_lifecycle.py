"""E2E test for goal pause/resume lifecycle.

Seeds a goal via container_exec, opens the Goals panel, and verifies
that the Pause and Resume buttons toggle the goal's status correctly.
Also verifies the goal can be deleted via the ConfirmButton two-click
pattern.
"""

import pytest
from playwright.sync_api import Page, expect

from e2e._helpers import container_exec
from e2e.pages import GoalsView


GOAL_DESCRIPTION = "E2E lifecycle test goal"


@pytest.fixture
def test_goal(page: Page):
    """Seed a goal with one noop task. Tears down on exit."""
    goal_id = container_exec(
        "from tasks import get_store\n"
        "s = get_store()\n"
        f"g = s.create_goal({GOAL_DESCRIPTION!r})\n"
        "s.create_task(g.id, 'lifecycle task', 'noop')\n"
        "print(g.id)\n"
    )
    yield goal_id
    page.request.delete(f"/api/goals/{goal_id}", fail_on_status_code=False)


def test_pause_and_resume_goal(page: Page, test_goal):
    """Pause an active goal via the UI, verify status changes, then resume."""
    goals = GoalsView(page).goto()
    goals.select_by_name(GOAL_DESCRIPTION)

    expect(goals.status_label()).to_contain_text("ACTIVE", timeout=5000)
    expect(goals.pause_button()).to_be_visible()

    goals.pause_button().click()
    expect(goals.status_label()).to_contain_text("PAUSED", timeout=5000)
    expect(goals.resume_button()).to_be_visible()

    goals.resume_button().click()
    expect(goals.status_label()).to_contain_text("ACTIVE", timeout=5000)
    expect(goals.pause_button()).to_be_visible()


def test_delete_goal(page: Page, test_goal):
    """Delete a goal via the two-click ConfirmButton and verify it's gone."""
    goals = GoalsView(page).goto()
    goals.select_by_name(GOAL_DESCRIPTION)
    expect(goals.status_label()).to_be_visible(timeout=5000)

    goals.delete_button().click()
    goals.confirm_button().click()
    page.wait_for_timeout(500)

    resp = page.request.get("/api/goals")
    all_goals = resp.json().get("goals", [])
    assert not any(g["id"] == test_goal for g in all_goals)
