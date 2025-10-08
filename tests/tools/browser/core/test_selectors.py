"""Unit tests for selector registry utilities."""

from __future__ import annotations

from typing import Callable
import pytest

from tools.browser.core import selectors


class _FakeLocator:
    """Test double for Playwright Locator."""

    def __init__(self, count: int) -> None:
        self._count = count

    async def count(self) -> int:
        """Return preconfigured count."""
        return self._count


class _FakePage:
    """Test double for Playwright Page."""

    def __init__(self, counts: dict[str, int] | None = None) -> None:
        self._counts = counts or {}

    def locator(self, selector: str) -> _FakeLocator:
        """Return locator with configured match count."""
        count = self._counts.get(selector, 1)
        return _FakeLocator(count)



class _FakeElementHandle:
    """Test double for Playwright ElementHandle."""

    def __init__(
        self,
        *,
        attributes: dict[str, str | None] | None = None,
        dom_path: str = "",
        dom_parent_selector: str = "body",
        dom_tag: str = "div",
        dom_nth: int = 1,
    ) -> None:
        self._attributes = attributes or {}
        self._dom_path = dom_path
        self._dom_parent_selector = dom_parent_selector
        self._dom_tag = dom_tag
        self._dom_nth = dom_nth

    async def get_attribute(self, name: str) -> str | None:
        """Return stored attribute value."""
        return self._attributes.get(name)

    async def evaluate(self, script: str) -> str | dict[str, int | str] | None:
        """Return canned evaluation results based on the script."""
        if "siblings.indexOf" in script:
            return {
                "tagName": self._dom_tag,
                "nth": self._dom_nth,
                "parentSelector": self._dom_parent_selector,
            }
        if "segments.join" in script:
            return self._dom_path
        raise AssertionError(f"Unexpected evaluation script: {script}")


@pytest.fixture
def fake_page() -> _FakePage:
    """Provide a default fake page with no special locator counts."""
    return _FakePage()


@pytest.fixture
def registry(fake_page: _FakePage) -> selectors.SelectorRegistry:
    """Provide a SelectorRegistry backed by the fake page."""
    return selectors.SelectorRegistry(fake_page)  # type: ignore[arg-type]


@pytest.fixture
def element_factory() -> Callable[..., _FakeElementHandle]:
    """Return a factory for creating _FakeElementHandle instances.

    Usage: element = element_factory(attributes=..., dom_path=..., ...)
    """
    def _factory(
        *,
        attributes: dict[str, str | None] | None = None,
        dom_path: str = "",
        dom_parent_selector: str = "body",
        dom_tag: str = "div",
        dom_nth: int = 1,
    ) -> _FakeElementHandle:
        return _FakeElementHandle(
            attributes=attributes,
            dom_path=dom_path,
            dom_parent_selector=dom_parent_selector,
            dom_tag=dom_tag,
            dom_nth=dom_nth,
        )

    return _factory


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_selector_prefers_id(registry: selectors.SelectorRegistry, element_factory: Callable[..., _FakeElementHandle]) -> None:
    """Registry should prefer id selector when available."""
    element = element_factory(attributes={"id": "primary"})

    result = await selectors.build_unique_selector(
        element,  # type: ignore[arg-type]
        tag="button",
        text="Click Me",
        registry=registry,
    )

    assert result.selector == "#primary"
    assert result.strategy == selectors.SelectorStrategy.ID
    assert result.collision_count == 0
    assert result.verified_unique is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_selector_uses_text_when_available(element_factory: Callable[..., _FakeElementHandle]) -> None:
    """Registry should emit text selector when it is uniquely verified."""
    page = _FakePage({'text="Submit"': 1})
    registry = selectors.SelectorRegistry(page)  # type: ignore[arg-type]
    element = element_factory(dom_path="body > button:nth-of-type(1)", dom_tag="button")

    result = await selectors.build_unique_selector(
        element,  # type: ignore[arg-type]
        tag="button",
        text="Submit",
        registry=registry,
    )

    assert result.selector == 'text="Submit"'
    assert result.strategy == selectors.SelectorStrategy.TEXT_EXACT
    assert result.verified_unique is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_selector_falls_back_without_text(element_factory: Callable[..., _FakeElementHandle]) -> None:
    """Registry should fall back to structural selectors when text is absent."""
    page = _FakePage({"#panel > button:nth-of-type(1)": 1})
    registry = selectors.SelectorRegistry(page)  # type: ignore[arg-type]
    element = element_factory(
        dom_path="#panel > button:nth-of-type(1)",
        dom_parent_selector="#panel",
        dom_tag="button",
        dom_nth=1,
    )

    result = await selectors.build_unique_selector(
        element,  # type: ignore[arg-type]
        tag="button",
        text=None,
        registry=registry,
    )

    assert result.strategy in (
        selectors.SelectorStrategy.DOM_POSITION,
        selectors.SelectorStrategy.DOM_PATH,
    )
    assert result.selector.startswith("#panel")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_selector_adds_fallback_suffix(element_factory: Callable[..., _FakeElementHandle]) -> None:
    """Registry should append nth fallback when all strategies collide."""
    page = _FakePage({"#panel > button:nth-of-type(1)": 2})
    registry = selectors.SelectorRegistry(page)  # type: ignore[arg-type]
    first = element_factory(
        dom_path="#panel > button:nth-of-type(1)",
        dom_parent_selector="#panel",
        dom_tag="button",
        dom_nth=1,
    )
    second = _FakeElementHandle(
        dom_path="#panel > button:nth-of-type(1)",
        dom_parent_selector="#panel",
        dom_tag="button",
        dom_nth=1,
    )

    first_result = await selectors.build_unique_selector(
        first,  # type: ignore[arg-type]
        tag="button",
        text=None,
        registry=registry,
    )
    second_result = await selectors.build_unique_selector(
        second,  # type: ignore[arg-type]
        tag="button",
        text=None,
        registry=registry,
    )

    assert first_result.strategy in (
        selectors.SelectorStrategy.DOM_POSITION,
        selectors.SelectorStrategy.DOM_PATH,
    )
    assert second_result.strategy == selectors.SelectorStrategy.FALLBACK
    assert second_result.selector.endswith(">> nth=1")
    assert second_result.collision_count >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_selector_prefers_data_attribute(registry: selectors.SelectorRegistry, element_factory: Callable[..., _FakeElementHandle]) -> None:
    """Registry should prefer data-* attributes when present."""
    element = element_factory(attributes={"data-testid": "widget-1"})

    result = await selectors.build_unique_selector(
        element,  # type: ignore[arg-type]
        tag="div",
        text=None,
        registry=registry,
    )

    assert result.strategy == selectors.SelectorStrategy.DATA_ATTRIBUTE
    assert result.selector == "[data-testid='widget-1']"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_selector_name_attribute_with_input_type(registry: selectors.SelectorRegistry, element_factory: Callable[..., _FakeElementHandle]) -> None:
    """Name selector for inputs should include type when available."""
    element = element_factory(attributes={"name": "email", "type": "email"})

    result = await selectors.build_unique_selector(
        element,  # type: ignore[arg-type]
        tag="input",
        text=None,
        registry=registry,
    )

    assert result.strategy == selectors.SelectorStrategy.NAME_ATTRIBUTE
    assert "input[type='email'][name='email']" == result.selector


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_selector_name_attribute_without_tag(registry: selectors.SelectorRegistry, element_factory: Callable[..., _FakeElementHandle]) -> None:
    """When no tag prefix is provided, name selector should be attribute-only."""
    element = element_factory(attributes={"name": "q"})

    # pass an empty tag to avoid evaluate() call in the implementation
    result = await selectors.build_unique_selector(
        element,  # type: ignore[arg-type]
        tag="",
        text=None,
        registry=registry,
    )

    assert result.strategy == selectors.SelectorStrategy.NAME_ATTRIBUTE
    assert result.selector == "[name='q']"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_selector_aria_role_label_verification(element_factory: Callable[..., _FakeElementHandle]) -> None:
    """ARIA role + label selector should be constructed and verified unique."""
    sel = "[role='button'][aria-label='Label']"
    page = _FakePage({sel: 1})
    registry = selectors.SelectorRegistry(page)  # type: ignore[arg-type]
    element = element_factory(attributes={"aria-label": "Label", "role": "button"})

    result = await selectors.build_unique_selector(
        element,  # type: ignore[arg-type]
        tag="button",
        text=None,
        registry=registry,
    )

    assert result.strategy == selectors.SelectorStrategy.ARIA_ROLE_LABEL
    assert result.verified_unique is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_text_selector_respects_length_limit(registry: selectors.SelectorRegistry, element_factory: Callable[..., _FakeElementHandle]) -> None:
    """Very long text should not produce a TEXT_EXACT selector."""
    long_text = "x" * (selectors.MAX_TEXT_SELECTOR_LEN + 10)
    element = element_factory(dom_path="#root > p:nth-of-type(1)", dom_tag="p")

    result = await selectors.build_unique_selector(
        element,  # type: ignore[arg-type]
        tag="p",
        text=long_text,
        registry=registry,
    )

    assert result.strategy != selectors.SelectorStrategy.TEXT_EXACT


@pytest.mark.unit
def test_registry_seen_and_reset() -> None:
    """Registry seen() should reflect issued selectors and reset() should clear."""
    registry = selectors.SelectorRegistry(_FakePage())  # type: ignore[arg-type]

    # simulate registering a selector by manipulating internal state via public API
    registry._seen["#a"] = 1
    assert "#a" in registry.seen()
    registry.reset()
    assert len(registry.seen()) == 0
