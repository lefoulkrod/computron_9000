import pytest

from tools.browser.core.snapshot import _build_page_snapshot


class _FakeField:
    def __init__(self, tag: str, name: str | None = None, type_: str | None = None, *, value: str | None = None, checked: bool = False, css: str | None = None) -> None:
        self._tag = tag
        self._name = name
        self._type = type_
        self._value = value
        self._checked = checked
        self._css = css or f"form > {tag}.{(name or tag or 'field')}"

    async def evaluate(self, script: str) -> object:  # noqa: D401
        # Simulate the minimal scripts used in snapshot extraction.
        if "tagName" in script:
            return self._tag
        if "el.checked === true" in script:
            return bool(self._checked)
        # If testing property access for value (el => el.value), return the stored value
        if "el.value" in script or "el => el.value" in script:
            return self._value
        return self._css

    async def get_attribute(self, name: str) -> str | None:  # noqa: D401
        if name == "name":
            return self._name
        if name == "type":
            return self._type
        if name == "value":
            return self._value
        if name == "checked":
            return "" if self._checked else None
        if name == "required":
            return "" if self._name == "username" else None
        return None

    async def evaluate_handle(self, script: str) -> None:  # noqa: D401
        return None


class _FakeOption:
    def __init__(self, value: str, label: str, selected: bool = False) -> None:
        self._value = value
        self._label = label
        self._selected = selected

    async def get_attribute(self, name: str) -> str | None:  # noqa: D401
        if name == "value":
            return self._value
        if name == "selected":
            return "" if self._selected else None
        return None

    async def inner_text(self) -> str:  # noqa: D401
        return self._label

    async def evaluate(self, script: str) -> object:  # noqa: D401
        if "o.selected === true" in script:
            return bool(self._selected)
        return None


class _FakeSelect(_FakeField):
    def __init__(self, name: str, options: list[_FakeOption]) -> None:
        super().__init__("select", name=name)
        self._options = options

    async def query_selector_all(self, selector: str) -> list:  # noqa: D401
        if selector == "option":
            return self._options
        return []


class _FakeForm:
    def __init__(self, fields: list[_FakeField]) -> None:
        self._fields = fields

    async def get_attribute(self, name: str) -> str | None:  # noqa: D401
        return None

    async def query_selector_all(self, selector: str) -> list:  # noqa: D401
        if selector == "input, textarea, select":
            return self._fields
        if selector.startswith("input[type='radio'][name="):
            # Return matching radios by name
            name = selector.split("[name='")[1][:-2]
            return [f for f in self._fields if getattr(f, "_type", None) == "radio" and getattr(f, "_name", None) == name]
        return []


class _FakePage:
    def __init__(self, forms: list[_FakeForm]) -> None:
        self._forms = forms
        self.url = "https://x"

    async def title(self) -> str:  # noqa: D401
        return "T"

    async def inner_text(self, selector: str) -> str:  # noqa: D401
        return "Body"

    async def query_selector_all(self, selector: str) -> list:  # noqa: D401
        if selector == "form":
            return self._forms
        if selector == "a":
            return []
        if selector == "button, [role=button]":
            return []
        if selector == "iframe":
            return []
        raise AssertionError(selector)


class _FakeResponse:
    def __init__(self) -> None:
        self.url = "https://x"
        self.status = 200


@pytest.mark.unit
@pytest.mark.asyncio
async def test_form_field_value_and_selected_flags() -> None:
    """Ensure value and selected fields are populated for different control types."""

    text_input = _FakeField("input", name="username", type_="text", value="alice")
    password_input = _FakeField("input", name="password", type_="password", value="secret")
    checkbox_input = _FakeField("input", name="agree_terms", type_="checkbox", checked=True, value="yes")
    radio1 = _FakeField("input", name="color", type_="radio", value="red", checked=True)
    radio2 = _FakeField("input", name="color", type_="radio", value="blue", checked=False)
    select = _FakeSelect(
        name="country",
        options=[
            _FakeOption("us", "United States", selected=True),
            _FakeOption("ca", "Canada", selected=False),
        ],
    )

    form = _FakeForm([text_input, password_input, checkbox_input, radio1, radio2, select])
    page = _FakePage([form])
    response = _FakeResponse()

    snap = await _build_page_snapshot(page, response)  # type: ignore[arg-type]
    form_entry = next(e for e in snap.elements if e.tag == "form")
    fields = {f.name: f for f in form_entry.fields or []}

    assert fields["username"].value == "alice"
    assert fields["password"].value == "secret"
    assert fields["agree_terms"].value == "yes"
    assert fields["agree_terms"].selected is True

    # Radio uniqueness & selection
    radio_fields = [f for f in form_entry.fields or [] if f.field_type == "radio" and f.name == "color"]
    assert len(radio_fields) == 2
    assert any(f.value == "red" and f.selected for f in radio_fields)
    assert any(f.value == "blue" and not f.selected for f in radio_fields)
    assert all(" >> nth=" in f.selector for f in radio_fields)

    # Select values & options with selected flag
    select_field = fields["country"]
    assert select_field.value == "us"  # selected option value
    assert select_field.options is not None
    opt_map = {o["value"]: o for o in select_field.options}
    assert opt_map["us"]["selected"] is True
    assert opt_map["ca"]["selected"] is False

    # Required flag propagated from username only
    assert fields["username"].required is True
    assert fields["password"].required is False
