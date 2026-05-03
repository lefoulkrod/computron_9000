"""POM for the Goals split-panel view."""

from playwright.sync_api import Locator, Page


class GoalsView:
    """Goals sidebar panel — list on the left, detail on the right."""

    def __init__(self, page: Page):
        self.page = page

    def goto(self) -> "GoalsView":
        self.page.goto("/")
        self.page.get_by_role("button", name="Goals", exact=True).click()
        self.page.locator("[class*='goalsList'], [class*='empty']").first.wait_for(state="visible")
        return self

    def select_by_name(self, description: str) -> None:
        self.page.get_by_text(description, exact=True).click()

    def pause_button(self) -> Locator:
        return self.page.get_by_role("button", name="Pause")

    def resume_button(self) -> Locator:
        return self.page.get_by_role("button", name="Resume")

    def run_now_button(self) -> Locator:
        return self.page.get_by_role("button", name="Run now")

    def delete_button(self) -> Locator:
        return self.page.get_by_title("Delete this goal")

    def confirm_button(self) -> Locator:
        return self.page.get_by_role("button", name="Confirm?")

    def status_label(self) -> Locator:
        return self.page.locator("[class*='activeLabel']")

    def empty_message(self) -> Locator:
        return self.page.locator("[class*='empty']")
