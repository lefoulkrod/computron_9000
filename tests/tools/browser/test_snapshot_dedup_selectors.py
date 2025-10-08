import pytest
from tools.browser.core.snapshot import _extract_elements, Element


class _FakeHandle:
    def __init__(
        self,
        tag: str,
        text: str | None,
        selector_css: str,
        role: str | None = None,
        attrs: dict[str, str] | None = None,
    ) -> None:
        self._tag = tag
        self._text = text or ""
        self._selector_css = selector_css
        self._role = role
        self._attrs = attrs or {}

    async def inner_text(self) -> str:  # noqa: D401
        return self._text

    async def get_attribute(self, name: str) -> str | None:  # noqa: D401
        # Supply per-element arbitrary attributes for clickable selection.
        if name in self._attrs:
            return self._attrs[name]
        # For this test we intentionally suppress anchor href so all three elements
        # resolve to a text-based selector and trigger global dedupe.
        if name == "href" and self._tag == "a":
            return None
        if name == "role":
            return self._role
        return None

    async def evaluate(self, script: str) -> str:  # noqa: D401
        if "tagName" in script:
            return self._tag
        # Visibility / hidden heuristic script contains 'offsetParent'; return False (not hidden)
        if "offsetParent" in script:
            return False  # type: ignore[return-value]
        return self._selector_css

    async def is_visible(self) -> bool:  # noqa: D401
        return True


class _FakePage:
    def __init__(self, buttons: list[_FakeHandle], anchors: list[_FakeHandle], clickables: list[_FakeHandle]):
        self._buttons = buttons
        self._anchors = anchors
        self._clickables = clickables

    async def query_selector_all(self, selector: str) -> list[_FakeHandle]:  # noqa: D401
        if selector == "button, [role=button]":
            return self._buttons
        if selector == "a":
            return self._anchors
        if selector == "iframe":
            return []
        if selector == "form":
            return []
        if selector == "div[onclick], span[onclick], li[onclick], [role='button'], [role='link'], [tabindex], [data-clickable]":
            return self._clickables
        raise AssertionError(selector)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_global_dedup_spans_categories() -> None:
    """Global dedupe adds nth suffix across categories (button vs clickable).

    Local (category) dedupe doesn't run because each category has only one
    element, but global pass should suffix the second identical selector.
    """
    shared_css = "body > main > div.buttonish"
    btn = _FakeHandle("button", "Action", shared_css)
    div_click = _FakeHandle("div", "Action", shared_css, attrs={"onclick": "do()"})
    page = _FakePage([btn], [], [div_click])
    elements = await _extract_elements(page, link_limit=10)  # type: ignore[arg-type]
    selectors = [e.selector for e in elements if e.text == "Action"]
    assert len(selectors) == 2
    # Expect first text selector unsuffixed, second suffixed by global dedupe
    assert selectors[0] == 'text="Action"'
    assert selectors[1] == 'text="Action" >> nth=0'
