import pytest

from tools.browser.core.snapshot import _build_page_snapshot, Element


class _FakeAnchor:
    def __init__(
        self,
        text: str,
        href: str,
        css: str | None = None,
        *,
        el_id: str | None = None,
        data_testid: str | None = None,
    ) -> None:
        self._text = text
        self._href = href
        self._id = el_id
        self._data_testid = data_testid
        # Provide a deterministic css path to mimic the in-page JS output.
        self._css = css or "body > header > nav > a.link"

    async def inner_text(self) -> str:  # noqa: D401
        return self._text

    async def get_attribute(self, name: str) -> str | None:  # noqa: D401
        if name == "href":
            return self._href
        if name == "id":
            return self._id
        if name == "data-testid":
            return self._data_testid
        return None

    async def evaluate(self, script: str) -> str:  # noqa: D401
        # The snapshot builder only expects the script to return a string selector.
        # Ignore the script contents and return our stored css path.
        return self._css


class _FakeField:
    def __init__(self, tag: str, name: str | None = None, type_: str | None = None) -> None:
        self._tag = tag
        self._name = name
        self._type = type_

    async def evaluate(self, script: str) -> str:  # noqa: D401
        return self._tag

    async def get_attribute(self, name: str) -> str | None:  # noqa: D401
        if name == "name":
            return self._name
        if name == "type":
            return self._type
        return None


class _FakeForm:
    def __init__(self, action: str | None, form_id: str | None, fields: list[_FakeField]):
        self._action = action
        self._id = form_id
        self._fields = fields

    async def get_attribute(self, name: str) -> str | None:
        if name == "action":
            return self._action
        if name == "id":
            return self._id
        return None

    async def query_selector_all(self, selector: str) -> list[_FakeField]:
        assert selector == "input, textarea, select"
        return self._fields


class _FakePage:
    def __init__(
        self,
        title: str,
        body: str,
        anchors: list[_FakeAnchor],
        forms: list[_FakeForm],
        url: str = "https://x",
    ):  # noqa: D401
        self._title = title
        self._body = body
        self._anchors = anchors
        self._forms = forms
        self.url = url

    async def title(self) -> str:  # noqa: D401
        return self._title

    async def inner_text(self, selector: str) -> str:  # noqa: D401
        assert selector == "body"
        return self._body

    async def query_selector_all(self, selector: str) -> list:  # noqa: D401
        if selector == "a":
            return self._anchors
        if selector == "form":
            return self._forms
        if selector in {"button, [role=button]", "iframe"}:
            return []
        raise AssertionError(selector)


class _FakeResponse:
    def __init__(self, url: str, status: int):
        self.url = url
        self.status = status


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_snapshot_truncation_and_filters() -> None:
    anchors = [_FakeAnchor(text="link" + str(i), href=f"https://h/{i}") for i in range(30)]
    # Add one empty
    anchors.append(_FakeAnchor(text="   ", href="https://h/zzz"))
    form = _FakeForm(
        action=None,
        form_id="login",
        fields=[
            _FakeField("input", name="username", type_="text"),
            _FakeField("input", name="ignored", type_="hidden"),
            _FakeField("input", name="password", type_="password"),
        ],
    )

    page = _FakePage(
        title="Title",
        body="a" * 600,
        anchors=anchors,
        forms=[form],
    )
    response = _FakeResponse(url="https://final", status=201)

    snap = await _build_page_snapshot(page, response)  # type: ignore[arg-type]
    assert snap.title == "Title"
    assert len(snap.snippet) == 500  # truncated
    assert snap.url == "https://final"
    assert snap.status_code == 201
    anchor_elements = [e for e in snap.elements if e.tag == "a"]
    form_elements = [e for e in snap.elements if e.tag == "form"]
    assert len(anchor_elements) == 20  # truncated
    assert all(isinstance(e, Element) for e in anchor_elements)
    assert form_elements[0].action is None
    assert form_elements[0].inputs == ["username", "password"]
    # CSS selector extraction should produce non-empty strings for anchors
    assert all(e.selector for e in anchor_elements)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fast_attribute_selectors() -> None:
    # Anchor with id should produce #id
    a1 = _FakeAnchor(text="Models", href="/models", el_id="models-link")
    # Anchor with data-testid should produce [data-testid='primary']
    a2 = _FakeAnchor(text="Login", href="/login", data_testid="primary")
    page = _FakePage(title="T", body="Body", anchors=[a1, a2], forms=[])
    response = _FakeResponse(url="https://x", status=200)
    snap = await _build_page_snapshot(page, response)  # type: ignore[arg-type]
    css_map = {e.text: e.selector for e in snap.elements if e.tag == "a"}
    assert css_map["Models"] in {"#models-link", "#models-link"}
    assert css_map["Login"].startswith("[data-testid='primary']")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_buttons_and_iframes_extracted() -> None:
    class _FakeButton:
        def __init__(self, text: str | None, role: str | None = None, css: str | None = None):
            self._text = text
            self._role = role
            self._css = css or "body > div > button.btn"

        async def inner_text(self) -> str:
            return self._text or ""

        async def get_attribute(self, name: str) -> str | None:
            if name == "role":
                return self._role
            if name == "id":
                return None
            return None

        async def evaluate(self, script: str) -> str:
            return self._css

    class _FakeIframe:
        def __init__(self, title: str | None, src: str | None, css: str | None = None):
            self._title = title
            self._src = src
            self._css = css or "body > div > iframe"

        async def get_attribute(self, name: str) -> str | None:
            if name == "title":
                return self._title
            if name == "src":
                return self._src
            return None

        async def evaluate(self, script: str) -> str:
            return self._css

    page = _FakePage(
        title="T",
        body="Body",
        anchors=[],
        forms=[],
    )

    # Monkeypatch query_selector_all to return buttons/iframes appropriately
    async def query_selector_all(selector: str) -> list:
        if selector == "button, [role=button]":
            return [_FakeButton("Click me", role=None), _FakeButton(None, role="button")]
        if selector == "a":
            return []
        if selector == "form":
            return []
        if selector == "iframe":
            return [_FakeIframe("Frame Title", "https://example.com/frame"), _FakeIframe(None, "https://sub.host/path")]
        raise AssertionError(selector)

    # Attach our custom query_selector_all onto page
    page.query_selector_all = query_selector_all  # type: ignore[method-assign]

    response = _FakeResponse(url="https://x", status=200)
    snap = await _build_page_snapshot(page, response)  # type: ignore[arg-type]

    btns = [e for e in snap.elements if e.tag == "button"]
    ifs = [e for e in snap.elements if e.tag == "iframe"]

    assert len(btns) == 2
    assert any(b.text == "Click me" for b in btns)
    # second button had no inner text; fallback label should exist
    assert any(b.text.startswith("Button #") for b in btns)

    assert len(ifs) == 2
    # first iframe should use title
    assert any(i.text == "Frame Title" and i.src and "example.com" in i.src for i in ifs)
    # second iframe should synthesize hostname label
    assert any(i.text.startswith("iframe ⇒ sub.host") for i in ifs)
