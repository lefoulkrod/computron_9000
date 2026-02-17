from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Sequence

try:  # pragma: no cover - under CI Playwright should be available
    from playwright.async_api import Error as PlaywrightError
except ModuleNotFoundError:  # pragma: no cover - testing fallback
    class PlaywrightError(Exception):
        """Fallback Playwright error stub used when Playwright is unavailable."""


class StubResponse:
    """Minimal response object mirroring the subset of attributes under test."""

    def __init__(self, url: str, status: int) -> None:
        self.url = url
        self.status = status


class _NavigationContext:
    """Async context manager returned by ``StubPage.expect_navigation``."""

    def __init__(self, page: "StubPage") -> None:
        self._page = page

    async def __aenter__(self) -> "_NavigationContext":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401 - parity with Playwright context manager
        return None

    @property
    def value(self) -> Awaitable[StubResponse]:  # noqa: D401 - Playwright returns awaitable response
        async def _get() -> StubResponse:
            return StubResponse(self._page.url, 200)

        return _get()


class StubElement:
    """Element stub that exposes ``inner_text`` returning stored content."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def inner_text(self) -> str:
        return self._text


class StubElementHandle:
    """Element handle stub supplying tag/type metadata for locator inspections."""

    def __init__(
        self,
        *,
        tag: str,
        input_type: str | None = None,
        bounding_box: dict[str, float] | None = None,
        frame: Any | None = None,
        dom_parent_selector: str = "body",
        dom_tag: str | None = None,
        dom_nth: int = 1,
        dom_path: str | None = None,
        text_value: str | None = None,
        attrs: dict[str, Any] | None = None,
        visible: bool = True,
    ) -> None:
        self._tag = tag
        self._input_type = input_type or "text"
        self._bounding_box = bounding_box
        self._frame = frame
        self._dom_tag = dom_tag or tag
        self._dom_parent_selector = dom_parent_selector
        self._dom_nth = dom_nth
        self._dom_path = dom_path or f"{dom_parent_selector} > {self._dom_tag}:nth-of-type({dom_nth})"
        self._visible = visible
        self._text_value = text_value or ""
        self._attrs = dict(attrs or {})

    async def evaluate(self, script: str) -> Any:
        if "siblings.indexOf" in script:
            return {
                "tagName": self._dom_tag,
                "nth": self._dom_nth,
                "parentSelector": self._dom_parent_selector,
            }
        if "segments.join" in script:
            return self._dom_path
        if "tagName" in script:
            return self._dom_tag
        # Support viewport check from viewport_only filtering
        if "getBoundingClientRect" in script and "window.innerHeight" in script:
            # Default to elements being in viewport for tests
            return True
        raise PlaywrightError(f"Unsupported evaluation script: {script}")

    async def get_attribute(self, name: str) -> str | None:
        if name == "type":
            return self._input_type
        return self._attrs.get(name)

    async def is_visible(self) -> bool:
        return self._visible

    async def inner_text(self) -> str:
        return self._text_value

    async def bounding_box(self) -> dict[str, float] | None:
        return self._bounding_box

    async def owner_frame(self) -> Any | None:
        return self._frame


class StubLocator:
    """Locator stub exposing the Playwright APIs touched by browser tool tests."""

    def __init__(
        self,
        page: "StubPage",
        *,
        key: str,
        present: bool = True,
        tag: str = "div",
        input_type: str | None = None,
        navigates_to: str | None = None,
        navigation_title: str | None = None,
        navigation_body: str | None = None,
        on_click: Callable[["StubPage", "StubLocator"], Awaitable[None] | None] | None = None,
        bounding_box: dict[str, float] | None = None,
        frame: Any | None = None,
        text_value: str | None = None,
        texts: Sequence[str] | None = None,
        dom_parent_selector: str = "body",
        dom_tag: str | None = None,
        dom_nth: int = 1,
        dom_path: str | None = None,
        role_name: str | None = None,
    ) -> None:
        self._page = page
        self.key = key
        self._present = present
        self._tag = tag
        self._input_type = input_type
        self._navigates_to = navigates_to
        self._navigation_title = navigation_title
        self._navigation_body = navigation_body
        self._on_click = on_click
        self._filled_value: str | None = None
        self.first = self
        self._bounding_box = bounding_box
        self._frame = frame
        self._text_value = text_value
        self._texts = list(texts or [])
        self._dom_parent_selector = dom_parent_selector
        self._dom_tag = dom_tag or tag
        self._dom_nth = dom_nth
        self._dom_path = dom_path or f"{dom_parent_selector} > {self._dom_tag}:nth-of-type({dom_nth})"
        self._role_name = role_name

    async def count(self) -> int:
        if not self._present:
            return 0
        if self._texts:
            return len(self._texts)
        return 1

    async def click(self, timeout: int | None = None, force: bool = False) -> None:
        if not self._present:
            raise PlaywrightError("element does not exist")
        if self._on_click is not None:
            result = self._on_click(self._page, self)
            if asyncio.iscoroutine(result):
                await result
        if self._navigates_to is not None:
            self._page._apply_navigation(
                url=self._navigates_to,
                title=self._navigation_title,
                body=self._navigation_body,
            )

    async def focus(self) -> None:
        return None

    async def element_handle(self, timeout: int | None = None) -> StubElementHandle | None:
        if not self._present:
            return None
        return StubElementHandle(
            tag=self._tag,
            input_type=self._input_type,
            bounding_box=self._bounding_box,
            frame=self._frame,
            dom_parent_selector=self._dom_parent_selector,
            dom_tag=self._dom_tag,
            dom_nth=self._dom_nth,
            dom_path=None,
        )

    async def element_handles(self) -> list[StubElementHandle]:
        handle = await self.element_handle()
        return [] if handle is None else [handle]

    async def fill(self, text: str) -> None:
        if not self._present:
            raise PlaywrightError("element does not exist")
        if self._tag not in {"input", "textarea"}:
            raise PlaywrightError("fill not supported for this element")
        if self._tag == "input" and self._input_type in {"checkbox", "radio", "file"}:
            raise PlaywrightError(f"unsupported input type: {self._input_type}")
        self._filled_value = text
        self._page.record_fill(text)

    async def type(self, text: str) -> None:
        if not self._present:
            raise PlaywrightError("element does not exist")
        self._filled_value = text
        self._page.record_fill(text)

    async def select_option(self, value: str | None = None, *, label: str | None = None) -> None:
        if not self._present:
            raise PlaywrightError("element does not exist")
        if self._tag != "select":
            raise PlaywrightError("select_option only valid for select elements")
        selected = label or value or ""
        self._filled_value = selected
        self._page.record_fill(selected)

    def nth(self, idx: int) -> "StubLocator | StubElement":
        if not self._texts:
            if idx == 0 and self._present:
                return self
            raise IndexError("locator has no multiple entries")
        return StubElement(self._texts[idx])

    async def inner_text(self) -> str:
        if not self._present:
            return ""
        if self._text_value is not None:
            return self._text_value
        if self._texts:
            return self._texts[0] if self._texts else ""
        return ""

    async def evaluate(self, script: str) -> Any:
        # Support the accessible-name probe used by _resolve_locator
        return self._text_value or self._role_name or ""

    async def wait_for(self, timeout: int | None = None) -> None:
        return None

    async def scroll_into_view_if_needed(self) -> None:
        return None

    async def all_text_contents(self) -> list[str]:
        return list(self._texts) if self._texts else []

    def locator(self, selector: str) -> "StubLocator":
        return StubLocator(self._page, key=f"{self.key} >> {selector}", present=False, tag="div")


class StubPage:
    """Shared Playwright-style page stub used by browser interaction tests."""

    def __init__(
        self,
        *,
        title: str = "Initial",
        body_text: str = "Default body",
        url: str = "https://example.test/start",
        final_url: str | None = None,
        status: int = 200,
    ) -> None:
        self._title = title
        self._body_text = body_text
        self.url = url
        self._text_locators: dict[str, StubLocator] = {}
        self._css_locators: dict[str, StubLocator] = {}
        self._role_locators: dict[str, list[StubLocator]] = {}
        self._all_locators: set[StubLocator] = set()
        self._nav_event = asyncio.Event()
        self.main_frame = object()
        self._final_url = final_url
        self._status = status
        self._closed = False
        self._scroll_state: dict[str, float | int] = {
            "scroll_top": 0,
            "viewport_height": 600,
            "document_height": 1200,
        }
        self._evaluate_overrides: dict[str, Any] = {}
        self.viewport_size = {"width": 1280, "height": 800}
        self._history: list[dict[str, Any]] = [{"url": url, "title": title, "body": body_text}]
        self._history_index: int = 0

    async def title(self) -> str:
        return self._title

    async def inner_text(self, selector: str) -> str:
        if selector == "body":
            return self._body_text
        raise PlaywrightError(f"Unsupported selector for inner_text: {selector}")

    async def wait_for_event(self, name: str, *, predicate: Any | None = None) -> Any:
        if name != "framenavigated":
            raise PlaywrightError(f"Unsupported event: {name}")
        await self._nav_event.wait()
        self._nav_event.clear()
        return None

    async def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        return None

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> StubResponse:
        final_url = self._final_url or url
        self._apply_navigation(url=final_url)
        return StubResponse(final_url, self._status)

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        if script in self._evaluate_overrides:
            result = self._evaluate_overrides[script]
            return result() if callable(result) else result
        # Handle annotated snapshot JS DOM walker (called with params dict)
        if isinstance(script, str) and "budget" in script and "scopeQuery" in script and arg is not None:
            return {"content": self._body_text, "truncated": False}
        # Handle viewport info query (used in snapshot building)
        if isinstance(script, str) and "scroll_top" in script and ("scrollY" in script or "scrollHeight" in script):
            # Return viewport data structure
            return {
                "scroll_top": self._scroll_state.get("scroll_top", 0),
                "viewport_height": self._scroll_state.get("viewport_height", 800),
                "viewport_width": self._scroll_state.get("viewport_width", 1280),
                "document_height": self._scroll_state.get("document_height", 2000),
            }
        # Handle viewport text extraction (optimized for LLM with structure)
        if isinstance(script, str) and ("querySelectorAll" in script or "innerText" in script) and "viewportHeight" in script:
            return self._body_text
        return None

    def get_by_role(self, role: str, *, name: str | None = None, exact: bool = True) -> StubLocator:
        key = f"role={role}[name={name}]" if name else f"role={role}"
        for loc in self._role_locators.get(role, []):
            if name is None:
                return loc
            if exact and loc._role_name == name:
                return loc
            if not exact and loc._role_name and name in loc._role_name:
                return loc
        return StubLocator(self, key=key, present=False)

    def get_by_text(self, text: str, *, exact: bool = True) -> StubLocator:
        return self._text_locators.get(text, StubLocator(self, key=f"text={text}", present=False))

    def locator(self, selector: str) -> StubLocator:
        if selector == "html":
            return StubLocator(self, key="html", present=True, tag="html")
        if ">> nth=" in selector:
            base, nth_part = selector.split(">> nth=", 1)
            base_selector = base.strip()
            try:
                index = int(nth_part.strip())
            except ValueError:
                index = 0
            base_locator = self.locator(base_selector)
            if isinstance(base_locator, StubLocator):
                texts = getattr(base_locator, "_texts", [])
                if texts:
                    if 0 <= index < len(texts):
                        element_text = texts[index]
                        return StubLocator(
                            self,
                            key=selector,
                            present=True,
                            tag=base_locator._tag,
                            text_value=element_text,
                            dom_parent_selector=base_locator._dom_parent_selector,
                            dom_tag=base_locator._dom_tag,
                            dom_nth=base_locator._dom_nth + index,
                            dom_path=base_locator._dom_path,
                        )
                    return StubLocator(self, key=selector, present=False)
                if base_locator._present:
                    return StubLocator(
                        self,
                        key=selector,
                        present=True,
                        tag=base_locator._tag,
                        dom_parent_selector=base_locator._dom_parent_selector,
                        dom_tag=base_locator._dom_tag,
                        dom_nth=base_locator._dom_nth,
                        dom_path=base_locator._dom_path,
                    )
            return StubLocator(self, key=selector, present=False)

        if selector in self._css_locators:
            return self._css_locators[selector]

        if selector.startswith("text="):
            raw = selector[len("text=") :]
            text = raw.strip('"')
            for key, loc in self._text_locators.items():
                if key == text:
                    return loc

        for loc in self._text_locators.values():
            if getattr(loc, "_dom_path", None) == selector:
                return loc

        return StubLocator(self, key=selector, present=False)

    async def wait_for_function(self, script: str, timeout: int | None = None) -> None:
        return None

    def add_text_locator(
        self,
        text: str,
        *,
        tag: str = "div",
        navigates_to: str | None = None,
        navigation_title: str | None = None,
        navigation_body: str | None = None,
        bounding_box: dict[str, float] | None = None,
        frame: Any | None = None,
        text_value: str | None = None,
        dom_parent_selector: str = "body",
        dom_path: str | None = None,
        dom_nth: int = 1,
    ) -> StubLocator:
        text_payload = text if text_value is None else text_value
        dom_tag = tag
        resolved_dom_path = dom_path or f"{dom_parent_selector} > {dom_tag}:nth-of-type({dom_nth})"
        locator = StubLocator(
            self,
            key=f"text={text}",
            present=True,
            tag=tag,
            navigates_to=navigates_to,
            navigation_title=navigation_title,
            navigation_body=navigation_body,
            bounding_box=bounding_box,
            frame=frame,
            text_value=text_payload,
            dom_parent_selector=dom_parent_selector,
            dom_tag=dom_tag,
            dom_nth=dom_nth,
            dom_path=resolved_dom_path,
        )
        self._text_locators[text] = locator
        self._all_locators.add(locator)
        return locator

    def add_css_locator(
        self,
        selector: str,
        *,
        tag: str = "div",
        input_type: str | None = None,
        navigates_to: str | None = None,
        navigation_title: str | None = None,
        navigation_body: str | None = None,
        bounding_box: dict[str, float] | None = None,
        frame: Any | None = None,
        text_value: str | None = None,
        texts: Sequence[str] | None = None,
        dom_parent_selector: str = "body",
        dom_path: str | None = None,
        dom_nth: int = 1,
    ) -> StubLocator:
        locator = StubLocator(
            self,
            key=selector,
            present=bool(texts) if texts is not None else True,
            tag=tag,
            input_type=input_type,
            navigates_to=navigates_to,
            navigation_title=navigation_title,
            navigation_body=navigation_body,
            bounding_box=bounding_box,
            frame=frame,
            text_value=text_value,
            texts=texts,
            dom_parent_selector=dom_parent_selector,
            dom_tag=tag,
            dom_nth=dom_nth,
            dom_path=dom_path,
        )
        self._css_locators[selector] = locator
        self._all_locators.add(locator)
        return locator

    def add_role_locator(
        self,
        role: str,
        *,
        name: str | None = None,
        tag: str = "div",
        input_type: str | None = None,
        navigates_to: str | None = None,
        navigation_title: str | None = None,
        navigation_body: str | None = None,
        bounding_box: dict[str, float] | None = None,
        text_value: str | None = None,
        texts: Sequence[str] | None = None,
    ) -> StubLocator:
        key = f"role={role}[name={name}]" if name else f"role={role}"
        locator = StubLocator(
            self,
            key=key,
            present=True,
            tag=tag,
            input_type=input_type,
            navigates_to=navigates_to,
            navigation_title=navigation_title,
            navigation_body=navigation_body,
            bounding_box=bounding_box,
            text_value=text_value,
            texts=texts,
            role_name=name,
        )
        self._role_locators.setdefault(role, []).append(locator)
        self._all_locators.add(locator)
        return locator

    def record_fill(self, value: str) -> None:
        self._body_text = f"Filled value: {value}"

    def _apply_navigation(
        self,
        *,
        url: str,
        title: str | None = None,
        body: str | None = None,
        record_history: bool = True,
    ) -> None:
        self.url = url
        if title is not None:
            self._title = title
        if body is not None:
            self._body_text = body
        if record_history:
            self._history = self._history[: self._history_index + 1]
            self._history.append({"url": self.url, "title": self._title, "body": self._body_text})
            self._history_index = len(self._history) - 1
        else:
            if 0 <= self._history_index < len(self._history):
                self._history[self._history_index] = {
                    "url": self.url,
                    "title": self._title,
                    "body": self._body_text,
                }
        self._nav_event.set()

    async def go_back(self, wait_until: str | None = None) -> None:
        if self._history_index == 0:
            return
        self._history_index -= 1
        entry = self._history[self._history_index]
        self._apply_navigation(
            url=entry.get("url", self.url),
            title=entry.get("title"),
            body=entry.get("body"),
            record_history=False,
        )

    async def go_back(self, wait_until: str | None = None) -> None:
        if not self._history:
            return
        self._history_index = max(0, self._history_index - 1)
        entry = self._history[self._history_index]
        self._apply_navigation(url=entry["url"], title=entry.get("title"), body=entry.get("body"))

    def expect_navigation(self, *args: Any, **kwargs: Any) -> _NavigationContext:
        return _NavigationContext(self)

    async def close(self) -> None:
        return None

    def mark_closed(self, closed: bool = True) -> None:
        self._closed = closed

    def is_closed(self) -> bool:
        return self._closed

    def set_scroll_state(
        self,
        *,
        scroll_top: float,
        viewport_height: float,
        document_height: float,
    ) -> None:
        self._scroll_state = {
            "scroll_top": scroll_top,
            "viewport_height": viewport_height,
            "document_height": document_height,
        }

    def register_evaluate_response(self, script: str, result: Any) -> None:
        self._evaluate_overrides[script] = result


class StubBrowser:
    """Minimal browser stub exposing ``current_page`` for interaction tests."""

    def __init__(self, page: StubPage) -> None:
        self._page = page

    async def current_page(self) -> StubPage:
        return self._page

    async def new_page(self) -> StubPage:
        return self._page

    async def perform_interaction(
        self,
        page: StubPage,
        action: Callable[[], Awaitable[Any]],
    ) -> "BrowserInteractionResult":
        """Match Browser.perform return contract for tests."""
        initial_url = getattr(page, "url", "")
        await action()
        final_url = getattr(page, "url", "")
        navigation = bool(initial_url and final_url and initial_url != final_url)
        reason = "browser-navigation" if navigation else "no-change"

        from config import load_config
        from tools.browser.core.browser import BrowserInteractionResult
        from tools.browser.core.waits import wait_for_page_settle as settle_helper

        waits = load_config().tools.browser.waits
        await settle_helper(page, expect_navigation=navigation, waits=waits)

        return BrowserInteractionResult(
            navigation=navigation,
            page_changed=navigation,
            reason=reason,
            navigation_response=None,
        )


