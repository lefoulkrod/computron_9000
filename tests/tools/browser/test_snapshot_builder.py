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

    async def is_visible(self) -> bool:  # noqa: D401 - all fake anchors visible
        return True


class _FakeField:
    def __init__(
        self,
        tag: str,
        name: str | None = None,
        type_: str | None = None,
        *,
        css: str | None = None,
    ) -> None:
        self._tag = tag
        self._name = name
        self._type = type_
        if css is None:
            suffix = (name or tag or "field").replace(" ", "-")
            css = f"form > {tag}.{suffix}"
        self._css = css

    async def evaluate(self, script: str) -> str:  # noqa: D401
        if "tagName" in script:
            return self._tag
        return self._css

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
        if selector == "input, textarea, select":
            return self._fields
        if selector.startswith("input[type='radio'][name='") and selector.endswith("']"):
            name = selector[len("input[type='radio'][name='"):-2]
            return [field for field in self._fields if getattr(field, "_type", None) == "radio" and getattr(field, "_name", None) == name]
        return []


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
        if selector == "button, [role=button]":
            return []
        if selector == "iframe":
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
    # New fields structure: ensure names and types are captured
    assert form_elements[0].fields is not None
    names = [f.name for f in form_elements[0].fields if f.field_type != "hidden"]
    assert names == ["username", "password"]
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
    locator_map = {e.text: e.selector for e in snap.elements if e.tag == "a"}
    assert locator_map["Models"] in {"#models-link", "#models-link"}
    assert locator_map["Login"].startswith("[data-testid='primary']")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_duplicate_text_anchors_get_distinct_selectors() -> None:
    a1_css = "body > header > a:nth-of-type(1)"
    a2_css = "body > footer > a:nth-of-type(2)"
    a1 = _FakeAnchor(text="Download", href="/download", css=a1_css)
    a2 = _FakeAnchor(text="Download", href="/download", css=a2_css)
    page = _FakePage(title="T", body="Body", anchors=[a1, a2], forms=[])
    response = _FakeResponse(url="https://x", status=200)
    snap = await _build_page_snapshot(page, response)  # type: ignore[arg-type]
    download_elements = [
        e.selector
        for e in snap.elements
        if e.tag == "a" and e.text.startswith("Download")
    ]
    assert len(download_elements) == 2
    selectors = set(download_elements)
    assert selectors == {
        "a[href='/download'] >> nth=0",
        "a[href='/download'] >> nth=1",
    }


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

        async def is_visible(self) -> bool:  # noqa: D401 - buttons visible
            return True

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

        async def is_visible(self) -> bool:  # noqa: D401 - iframes visible
            return True

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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_form_field_metadata_extracted() -> None:
    """Verify placeholder, required flag, and select options are captured."""

    class _FakeSelectOption:
        def __init__(self, value: str, text: str):
            self._value = value
            self._text = text
            self._selected = False

        async def get_attribute(self, name: str) -> str | None:
            if name == "value":
                return self._value
            return None

        async def inner_text(self) -> str:
            return self._text

        async def evaluate(self, script: str) -> object:  # noqa: D401
            if "o.selected" in script:
                return bool(self._selected)
            return None


    class _FakeSelect:
        def __init__(self, name: str, options: list[_FakeSelectOption]):
            self._name = name
            self._options = options

        async def evaluate(self, script: str) -> str:
            return "select"

        async def get_attribute(self, name: str) -> str | None:
            if name == "name":
                return self._name
            return None

        async def query_selector_all(self, selector: str) -> list[_FakeSelectOption]:
            assert selector == "option"
            return self._options


    class _FakeInput:
        def __init__(self, name: str, type_: str, placeholder: str | None = None, required: bool = False):
            self._name = name
            self._type = type_
            self._placeholder = placeholder
            self._required = required

        async def evaluate(self, script: str) -> str:
            return "input"

        async def get_attribute(self, name: str) -> str | None:
            if name == "name":
                return self._name
            if name == "type":
                return self._type
            if name == "placeholder":
                return self._placeholder
            if name == "required":
                return "" if self._required else None
            return None


    fake_select = _FakeSelect("country", [
        _FakeSelectOption("us", "United States"),
        _FakeSelectOption("ca", "Canada"),
    ])
    fake_input = _FakeInput("email", "email", placeholder="you@example.com", required=True)

    class _FakeForm2:
        def __init__(self) -> None:
            self._action = None

        async def get_attribute(self, name: str) -> str | None:
            if name == "action":
                return None
            if name == "id":
                return None
            return None

        async def query_selector_all(self, selector: str) -> list:
            # return our two controls
            assert selector == "input, textarea, select"
            return [fake_input, fake_select]

    page = _FakePage(
        title="T",
        body="Body",
        anchors=[],
        forms=[_FakeForm2()],  # type: ignore[list-item]
    )

    response = _FakeResponse(url="https://x", status=200)
    snap = await _build_page_snapshot(page, response)  # type: ignore[arg-type]

    forms = [e for e in snap.elements if e.tag == "form"]
    assert forms
    fields = forms[0].fields or []
    # Expect two fields: email and country (select)
    names = [f.name for f in fields]
    assert "email" in names and "country" in names
    email_field = next(f for f in fields if f.name == "email")
    assert email_field.placeholder == "you@example.com"
    assert email_field.required is True
    country_field = next(f for f in fields if f.name == "country")
    assert country_field.options is not None
    assert any(o["value"] == "us" and o["label"] == "United States" for o in country_field.options)


class _FakeLabelHandle:
    def __init__(self, text: str) -> None:
        self._text = text

    async def inner_text(self) -> str:
        return self._text


class _FakeRadioField(_FakeField):
    def __init__(
        self,
        *,
        name: str,
        value: str,
        label: str,
        checked: bool = False,
        css: str | None = None,
    ) -> None:
        super().__init__("input", name=name, type_="radio", css=css)
        self._value = value
        self._label = label
        self._checked = checked

    async def get_attribute(self, name: str) -> str | None:
        if name == "value":
            return self._value
        if name == "checked":
            return "" if self._checked else None
        return await super().get_attribute(name)

    async def evaluate_handle(self, script: str):  # noqa: D401
        if "closest('label')" in script:
            return _FakeLabelHandle(self._label)
        return None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_form_field_selectors_are_unique_across_forms() -> None:
    """Ensure duplicate field names fall back to scoped selectors."""

    css_form_one = "form[action='/newsletter/signup'] input[name='signup_email']"
    css_form_two = "form[action='/support/contact'] input[name='signup_email']"

    newsletter_form = _FakeForm(
        action="/newsletter/signup",
        form_id=None,
        fields=[
            _FakeField(
                "input",
                name="signup_email",
                type_="email",
                css=css_form_one,
            )
        ],
    )
    support_form = _FakeForm(
        action="/support/contact",
        form_id=None,
        fields=[
            _FakeField(
                "input",
                name="signup_email",
                type_="email",
                css=css_form_two,
            )
        ],
    )

    page = _FakePage(
        title="T",
        body="Body",
        anchors=[],
        forms=[newsletter_form, support_form],
    )

    response = _FakeResponse(url="https://x", status=200)
    snap = await _build_page_snapshot(page, response)  # type: ignore[arg-type]

    all_fields = [
        (form.text, field.selector)
        for form in snap.elements
        if form.tag == "form" and form.fields
        for field in form.fields
    ]

    selectors = [selector for _, selector in all_fields if selector]
    assert len(selectors) == len(set(selectors))

    selectors_by_form: dict[str, list[str]] = {}
    for form_label, selector in all_fields:
        if selector:
            selectors_by_form.setdefault(form_label, []).append(selector)

    newsletter_selectors = selectors_by_form.get("form[action='/newsletter/signup']", [])
    support_selectors = selectors_by_form.get("form[action='/support/contact']", [])

    assert newsletter_selectors == [css_form_one]
    assert support_selectors == [css_form_two]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_duplicate_fields_inside_single_form_use_distinct_selectors() -> None:
    """Controls sharing the same name within a form should still have unique selectors."""

    css_radio_one = "form[action='/preferences'] input[type='radio'][value='daily']"
    css_radio_two = "form[action='/preferences'] input[type='radio'][value='weekly']"

    class _FakeRadio(_FakeField):
        def __init__(self, value: str, css: str) -> None:
            super().__init__(
                "input",
                name="frequency",
                type_="radio",
                css=css,
            )
            self._value = value

        async def get_attribute(self, name: str) -> str | None:
            if name == "value":
                return self._value
            return await super().get_attribute(name)

        async def evaluate_handle(self, script: str):  # noqa: D401
            return None

    preferences_form = _FakeForm(
        action="/preferences",
        form_id=None,
        fields=[
            _FakeRadio("daily", css_radio_one),
            _FakeRadio("weekly", css_radio_two),
        ],
    )

    page = _FakePage(
        title="T",
        body="Body",
        anchors=[],
        forms=[preferences_form],
    )

    response = _FakeResponse(url="https://x", status=200)
    snap = await _build_page_snapshot(page, response)  # type: ignore[arg-type]

    form_entry = next(e for e in snap.elements if e.tag == "form" and e.fields)
    selectors = [field.selector for field in form_entry.fields or [] if field.selector]
    assert len(selectors) == len(set(selectors))
    assert selectors == [
        "input[type='radio'][name='frequency'] >> nth=0",
        "input[type='radio'][name='frequency'] >> nth=1",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_duplicate_fallback_selectors_gain_nth_suffix() -> None:
    """If fallback CSS collides, ensure nth suffix disambiguates selectors."""

    base_css = "form[action='/dup'] input.same"

    class _BasicField(_FakeField):
        def __init__(self) -> None:
            super().__init__(
                "input",
                name=None,
                type_=None,
                css=base_css,
            )

        async def get_attribute(self, name: str) -> str | None:
            return None

    dup_form = _FakeForm(
        action="/dup",
        form_id=None,
        fields=[_BasicField(), _BasicField()],
    )

    page = _FakePage(
        title="T",
        body="Body",
        anchors=[],
        forms=[dup_form],
    )

    response = _FakeResponse(url="https://x", status=200)
    snap = await _build_page_snapshot(page, response)  # type: ignore[arg-type]

    form_entry = next(e for e in snap.elements if e.tag == "form" and e.fields)
    selectors = [field.selector for field in form_entry.fields or [] if field.selector]
    assert len(selectors) == 2
    assert len(set(selectors)) == 2
    assert any(sel.endswith(" >> nth=0") for sel in selectors)
    assert base_css in selectors
