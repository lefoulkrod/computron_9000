from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Sequence

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


@dataclass
class StubField:
    """Form field stub mirroring the API surface used in tests."""

    tag: str
    name: str | None = None
    input_type: str | None = None
    dom_parent_selector: str = "form"
    dom_tag: str | None = None
    dom_nth: int = 1
    dom_path: str | None = None

    def __post_init__(self) -> None:
        if self.dom_tag is None:
            self.dom_tag = self.tag
        if self.dom_path is None:
            self.dom_path = f"{self.dom_parent_selector} > {self.dom_tag}:nth-of-type({self.dom_nth})"

    async def evaluate(self, script: str) -> Any:
        if "siblings.indexOf" in script:
            return {
                "tagName": self.dom_tag,
                "nth": self.dom_nth,
                "parentSelector": self.dom_parent_selector,
            }
        if "segments.join" in script:
            return self.dom_path
        if "tagName" in script:
            return self.tag
        return None

    async def get_attribute(self, name: str) -> str | None:
        if name == "name":
            return self.name
        if name == "type":
            return self.input_type
        return None


class StubForm:
    """Simple form stub returning stored attributes and fields."""

    def __init__(
        self,
        *,
        action: str | None,
        form_id: str | None,
        fields: Sequence[StubField],
        dom_parent_selector: str = "body",
        dom_tag: str = "form",
        dom_nth: int = 1,
        dom_path: str | None = None,
    ) -> None:
        self._action = action
        self._id = form_id
        self._fields = list(fields)
        self._dom_parent_selector = dom_parent_selector
        self._dom_tag = dom_tag
        self._dom_nth = dom_nth
        self._dom_path = dom_path or f"{dom_parent_selector} > {dom_tag}:nth-of-type({dom_nth})"
        self._set_dom_position(self._dom_parent_selector, self._dom_nth, dom_path=self._dom_path)

    async def get_attribute(self, name: str) -> str | None:
        if name == "action":
            return self._action
        if name == "id":
            return self._id
        return None

    async def evaluate(self, script: str) -> Any:
        if "siblings.indexOf" in script:
            return {
                "tagName": self._dom_tag,
                "nth": self._dom_nth,
                "parentSelector": self._dom_parent_selector,
            }
        if "segments.join" in script:
            return self._dom_path
        return None

    async def query_selector_all(self, selector: str) -> list[StubField]:
        if selector == "input, textarea, select":
            return list(self._fields)
        raise PlaywrightError(f"Unsupported selector for StubForm: {selector}")

    def _set_dom_position(self, parent_selector: str, nth: int, *, dom_path: str | None = None) -> None:
        self._dom_parent_selector = parent_selector
        self._dom_nth = nth
        self._dom_path = dom_path or f"{parent_selector} > {self._dom_tag}:nth-of-type({nth})"
        for idx, field in enumerate(self._fields, start=1):
            field.dom_parent_selector = self._dom_path
            field.dom_nth = idx
            field.dom_path = f"{self._dom_path} > {field.dom_tag}:nth-of-type({field.dom_nth})"


class StubAnchor:
    """Lightweight anchor stub supporting the subset of APIs used in tests."""

    def __init__(
        self,
        text: str,
        href: str,
        *,
        visible: bool = True,
        dom_parent_selector: str = "body",
        dom_tag: str = "a",
        dom_nth: int = 1,
        dom_path: str | None = None,
    ) -> None:
        self._text = text
        self._href = href
        self._visible = visible
        self._dom_parent_selector = dom_parent_selector
        self._dom_tag = dom_tag
        self._dom_nth = dom_nth
        self._dom_path = dom_path or f"{dom_parent_selector} > {dom_tag}:nth-of-type({dom_nth})"
        self._set_dom_position(self._dom_parent_selector, self._dom_nth, dom_path=self._dom_path)

    async def inner_text(self) -> str:
        return self._text

    async def get_attribute(self, name: str) -> str | None:
        if name == "href":
            return self._href
        return None

    async def is_visible(self) -> bool:
        return self._visible

    async def evaluate(self, script: str) -> Any:
        if "siblings.indexOf" in script:
            return {
                "tagName": self._dom_tag,
                "nth": self._dom_nth,
                "parentSelector": self._dom_parent_selector,
            }
        if "segments.join" in script:
            return self._dom_path
        return None

    def _set_dom_position(self, parent_selector: str, nth: int, *, dom_path: str | None = None) -> None:
        self._dom_parent_selector = parent_selector
        self._dom_nth = nth
        self._dom_path = dom_path or f"{parent_selector} > {self._dom_tag}:nth-of-type({nth})"


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
    ) -> None:
        self._tag = tag
        self._input_type = input_type or "text"
        self._bounding_box = bounding_box
        self._frame = frame
        self._dom_tag = dom_tag or tag
        self._dom_parent_selector = dom_parent_selector
        self._dom_nth = dom_nth
        self._dom_path = dom_path or f"{dom_parent_selector} > {self._dom_tag}:nth-of-type({dom_nth})"

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
        raise PlaywrightError(f"Unsupported evaluation script: {script}")

    async def get_attribute(self, name: str) -> str | None:
        if name == "type":
            return self._input_type
        return None

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

    async def count(self) -> int:
        if not self._present:
            return 0
        if self._texts:
            return len(self._texts)
        return 1

    async def click(self) -> None:
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

    async def element_handle(self) -> StubElementHandle | None:
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
            dom_path=self._dom_path,
        )

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

    async def select_option(self, value: str) -> None:
        if not self._present:
            raise PlaywrightError("element does not exist")
        if self._tag != "select":
            raise PlaywrightError("select_option only valid for select elements")
        self._filled_value = value
        self._page.record_fill(value)

    def nth(self, idx: int) -> StubElement:
        if not self._texts:
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

    async def wait_for(self, timeout: int | None = None) -> None:
        return None


class StubPage:
    """Shared Playwright-style page stub used by browser interaction tests."""

    def __init__(
        self,
        *,
        title: str = "Initial",
        body_text: str = "Default body",
        url: str = "https://example.test/start",
        anchors: Iterable[StubAnchor] | None = None,
        forms: Iterable[StubForm] | None = None,
        final_url: str | None = None,
        status: int = 200,
    ) -> None:
        self._title = title
        self._body_text = body_text
        self.url = url
        self._anchors = list(anchors or [])
        self._forms = list(forms or [])
        self._text_locators: dict[str, StubLocator] = {}
        self._css_locators: dict[str, StubLocator] = {}
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
        for idx, anchor in enumerate(self._anchors, start=1):
            if hasattr(anchor, "_set_dom_position"):
                parent = getattr(anchor, "_dom_parent_selector", "body")
                anchor._set_dom_position(parent, idx)
        for idx, form in enumerate(self._forms, start=1):
            if hasattr(form, "_set_dom_position"):
                parent = getattr(form, "_dom_parent_selector", "body")
                form._set_dom_position(parent, idx)

    async def title(self) -> str:
        return self._title

    async def inner_text(self, selector: str) -> str:
        if selector == "body":
            return self._body_text
        raise PlaywrightError(f"Unsupported selector for inner_text: {selector}")

    async def query_selector_all(self, selector: str) -> list[Any]:
        if selector == "a":
            return list(self._anchors)
        if selector == "form":
            return list(self._forms)
        if selector in {"button, [role=button]", "iframe"}:
            return []
        if selector in {
            "div[onclick], span[onclick], li[onclick], [role='link'], [tabindex], [data-clickable]"
        }:
            return []
        raise PlaywrightError(f"Unsupported selector: {selector}")

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
        self.url = final_url
        return StubResponse(final_url, self._status)

    async def evaluate(self, script: str) -> Any:
        if script in self._evaluate_overrides:
            result = self._evaluate_overrides[script]
            return result() if callable(result) else result
        if isinstance(script, str) and "scroll_top" in script and "window.scrollY" in script:
            return dict(self._scroll_state)
        return None

    def get_by_text(self, text: str, *, exact: bool = True) -> StubLocator:
        return self._text_locators.get(text, StubLocator(self, key=f"text={text}", present=False))

    def locator(self, selector: str) -> StubLocator:
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
            for anchor in self._anchors:
                if hasattr(anchor, "inner_text"):
                    anchor_text = getattr(anchor, "_text", None)
                    if anchor_text == text:
                        return StubLocator(self, key=selector, present=True, tag="a")
            for key, loc in self._text_locators.items():
                if key == text:
                    return loc

        for anchor in self._anchors:
            if getattr(anchor, "_dom_path", None) == selector:
                return StubLocator(self, key=selector, present=True, tag="a")

        for loc in self._text_locators.values():
            if getattr(loc, "_dom_path", None) == selector:
                return loc

        for form in self._forms:
            if getattr(form, "_dom_path", None) == selector:
                return StubLocator(self, key=selector, present=True, tag="form")
            for field in getattr(form, "_fields", []):
                if getattr(field, "dom_path", None) == selector:
                    return StubLocator(self, key=selector, present=True, tag=field.tag)

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

    def add_anchor(self, text: str, href: str, *, visible: bool = True) -> StubAnchor:
        nth = sum(1 for existing in self._anchors if isinstance(existing, StubAnchor)) + 1
        anchor = StubAnchor(text, href, visible=visible, dom_nth=nth)
        parent = getattr(anchor, "_dom_parent_selector", "body")
        anchor._set_dom_position(parent, nth)
        self._anchors.append(anchor)
        return anchor

    def add_form(self, *, action: str | None, form_id: str | None, fields: Iterable[StubField]) -> StubForm:
        nth = sum(1 for existing in self._forms if isinstance(existing, StubForm)) + 1
        form = StubForm(action=action, form_id=form_id, fields=list(fields), dom_nth=nth)
        parent = getattr(form, "_dom_parent_selector", "body")
        form._set_dom_position(parent, nth)
        self._forms.append(form)
        return form

    def record_fill(self, value: str) -> None:
        self._body_text = f"Filled value: {value}"

    def _apply_navigation(
        self,
        *,
        url: str,
        title: str | None = None,
        body: str | None = None,
    ) -> None:
        self.url = url
        if title is not None:
            self._title = title
        if body is not None:
            self._body_text = body
        self._nav_event.set()

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


class StubBrowserWithPages:
    """Browser stub that manages a list of pages and returns the newest open page."""

    def __init__(self, pages: Sequence[StubPage] | None = None) -> None:
        self._pages = list(pages or [])

    async def current_page(self) -> StubPage:
        for page in reversed(self._pages):
            is_closed = getattr(page, "is_closed", None)
            if callable(is_closed):
                if not is_closed():
                    return page
            else:
                return page
        raise RuntimeError("No open pages available in browser context")

    async def pages(self) -> list[StubPage]:
        return list(self._pages)
