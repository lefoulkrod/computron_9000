import pytest
from typing import Any

from tools.browser.core.snapshot import _collect_clickables


class _Node:
    def __init__(self, tag: str, *, text: str = "", attrs: dict[str, str] | None = None, visible: bool = True):
        self._tag = tag
        self._text = text
        self._attrs = attrs or {}
        self._visible = visible

    async def evaluate(self, script: str) -> Any:  # noqa: D401
        if script.startswith("el => el.tagName"):
            return self._tag
        # custom hidden heuristic removed; no extra flags
        return None

    async def is_visible(self) -> bool:  # noqa: D401
        return self._visible

    async def inner_text(self) -> str:  # noqa: D401
        return self._text

    async def get_attribute(self, name: str) -> str | None:  # noqa: D401
        return self._attrs.get(name)


class _Page:
    def __init__(self, nodes: list[_Node]):
        self._nodes = nodes

    async def query_selector_all(self, selector: str) -> list[_Node]:  # noqa: D401
        # naive: return nodes whose attrs cause them to be selected per heuristic list
        # We mimic combined comma selector by returning all nodes that satisfy any predicate.
        selected: list[_Node] = []
        for n in self._nodes:
            if n._tag in {"a", "button", "input", "select", "textarea", "form", "iframe"}:
                continue
            # attribute presence checks
            if ("onclick" in n._attrs) or (n._attrs.get("role") in {"button", "link"}) or ("tabindex" in n._attrs) or ("data-clickable" in n._attrs):
                selected.append(n)
        return selected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_clickables_basic_and_limit() -> None:
    nodes = [
        _Node("div", text="Primary CTA", attrs={"onclick": "do()"}),
        _Node("span", text="", attrs={"role": "button", "aria-label": "Icon Action"}),
        _Node("li", text="Repeated", attrs={"onclick": "x()"}),
        _Node("li", text="Repeated", attrs={"onclick": "y()"}),  # duplicate label
    _Node("div", text="Hidden", attrs={"onclick": "z()"}, visible=False),  # invisible skipped by is_visible
    ]
    page = _Page(nodes)
    # limit to 3 to test early stop
    els = await _collect_clickables(page, limit=3)  # type: ignore[arg-type]
    assert len(els) == 3
    labels = [e.text for e in els]
    assert any("Primary CTA" in l for l in labels)
    assert any("Icon Action" in l for l in labels)  # aria-label fallback


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_clickables_dedup_selectors() -> None:
    # Two nodes with same raw text and no attr uniqueness should get nth selectors
    nodes = [
        _Node("div", text="Duplicate", attrs={"onclick": "a()"}),
        _Node("div", text="Duplicate", attrs={"onclick": "b()"}),
    ]
    page = _Page(nodes)
    els = await _collect_clickables(page)  # type: ignore[arg-type]
    assert len(els) == 2
    # ensure selectors differ
    assert els[0].selector != els[1].selector


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_clickables_no_extra_hidden_heuristic() -> None:
    # Element that would previously be filtered only by custom hidden heuristic should now pass if visible.
    nodes = [
        _Node("div", text="Visible Node", attrs={"onclick": "a()"}, visible=True),
    ]
    page = _Page(nodes)
    els = await _collect_clickables(page)  # type: ignore[arg-type]
    assert len(els) == 1
    assert els[0].text.startswith("Visible Node")
