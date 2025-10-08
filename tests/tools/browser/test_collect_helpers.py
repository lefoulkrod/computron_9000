import pytest
from typing import Any

from tools.browser.core.snapshot import (
    _collect_anchors,
    _collect_buttons,
    _collect_iframes,
    _collect_forms,
)


class _StubHandle:
    def __init__(
        self,
        text: str | None = None,
        role: str | None = None,
        title: str | None = None,
        src: str | None = None,
        tag: str = "button",
        attrs: dict[str, Any] | None = None,
        visible: bool = True,
    ) -> None:
        self._text = text
        self._role = role
        self._title = title
        self._src = src
        self._tag = tag
        self._attrs = attrs or {}
        self._visible = visible

    async def inner_text(self) -> str:
        return self._text or ""

    async def get_attribute(self, name: str) -> str | None:
        if name == "role":
            return self._role
        if name == "title":
            return self._title
        if name == "src":
            return self._src
        return self._attrs.get(name)

    async def evaluate(self, script: str) -> str:  # minimal path return
        if "tagName" in script:
            return self._tag
        return "body > stub > elem"

    async def is_visible(self) -> bool:
        return self._visible

    async def query_selector_all(self, selector: str) -> list[Any]:  # only used by forms helper
        return []


class _StubPage:
    def __init__(
        self,
        *,
        buttons: list[_StubHandle] | None = None,
        iframes: list[_StubHandle] | None = None,
        forms: list[_StubHandle] | None = None,
        anchors: list[_StubHandle] | None = None,
    ) -> None:
        self._buttons = buttons or []
        self._iframes = iframes or []
        self._forms = forms or []
        self._anchors = anchors or []

    async def query_selector_all(self, selector: str) -> list[Any]:
        if selector == "button, [role=button]":
            return self._buttons
        if selector == "iframe":
            return self._iframes
        if selector == "form":
            return self._forms
        if selector == "a":
            return self._anchors
        if selector == "input, textarea, select":  # for forms fields
            return []
        raise AssertionError(selector)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_buttons_labels_and_dedupe() -> None:
    btn1 = _StubHandle(text="Submit", tag="button")
    btn2 = _StubHandle(text="Submit", tag="button")  # duplicate text triggers nth
    page = _StubPage(buttons=[btn1, btn2])
    els = await _collect_buttons(page)  # type: ignore[arg-type]
    assert len(els) == 2
    assert all(e.tag == "button" for e in els)
    selectors = [e.selector for e in els]
    assert selectors[0] != selectors[1]  # de-duplicated with nth suffix


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_buttons_skips_hidden() -> None:
    visible = _StubHandle(text="Visible", tag="button", visible=True)
    hidden = _StubHandle(text="Hidden", tag="button", visible=False)
    page = _StubPage(buttons=[visible, hidden])
    els = await _collect_buttons(page)  # type: ignore[arg-type]
    assert len(els) == 1
    assert els[0].text.startswith("Visible")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_iframes_title_and_hostname() -> None:
    iframe1 = _StubHandle(title="Main Frame", src="https://example.com", tag="iframe")
    iframe2 = _StubHandle(title=None, src="https://sub.host/path", tag="iframe")
    page = _StubPage(iframes=[iframe1, iframe2])
    els = await _collect_iframes(page)  # type: ignore[arg-type]
    assert len(els) == 2
    texts = {e.text for e in els}
    assert "Main Frame" in texts
    assert any(t.startswith("iframe ⇒ sub.host") for t in texts)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_forms_basic_structure() -> None:
    class _Form(_StubHandle):
        def __init__(self, action: str | None = None, form_id: str | None = None) -> None:
            super().__init__(tag="form", attrs={"action": action, "id": form_id})

    form1 = _Form(action="/login")
    page = _StubPage(forms=[form1])
    els = await _collect_forms(page)  # type: ignore[arg-type]
    assert len(els) == 1
    form_el = els[0]
    assert form_el.tag == "form"
    assert form_el.action == "/login"
    assert form_el.fields == [] or form_el.fields is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_anchors_skips_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    visible = _StubHandle(text="Visible Link", tag="a", attrs={"href": "https://ex.com"}, visible=True)
    hidden = _StubHandle(text="Hidden Link", tag="a", attrs={"href": "https://ex.com/hidden"}, visible=False)
    page = _StubPage(anchors=[visible, hidden])

    async def fake_resolve(handle: _StubHandle, *, tag: str | None, text: str, text_unique: bool) -> str:
        return f"selector-{handle._attrs.get('href', '')}"

    async def fake_best(handle: _StubHandle, tag: str | None = None) -> str:
        return f"best-{handle._attrs.get('href', '')}"

    monkeypatch.setattr("tools.browser.core.snapshot._resolve_element_selector", fake_resolve)
    monkeypatch.setattr("tools.browser.core.snapshot._best_selector", fake_best)

    els = await _collect_anchors(page)  # type: ignore[arg-type]
    assert len(els) == 1
    assert els[0].href == "https://ex.com"
