import pytest

from tools.browser.core.snapshot import _build_page_snapshot, Link, Form


class _FakeAnchor:
    def __init__(self, text: str, href: str) -> None:
        self._text = text
        self._href = href

    async def inner_text(self) -> str:
        return self._text

    async def get_attribute(self, name: str) -> str | None:
        if name == "href":
            return self._href
        return None


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

    async def query_selector_all(self, selector: str):  # noqa: D401
        if selector == "a":
            return self._anchors
        if selector == "form":
            return self._forms
        raise AssertionError


class _FakeResponse:
    def __init__(self, url: str, status: int):
        self.url = url
        self.status = status


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_snapshot_truncation_and_filters():
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

    snap = await _build_page_snapshot(page, response)
    assert snap.title == "Title"
    assert len(snap.snippet) == 500  # truncated
    assert snap.url == "https://final"
    assert snap.status_code == 201
    assert len(snap.links) == 20  # truncated
    assert all(isinstance(l, Link) for l in snap.links)
    assert snap.forms[0].selector == "form#login"
    assert snap.forms[0].inputs == ["username", "password"]
