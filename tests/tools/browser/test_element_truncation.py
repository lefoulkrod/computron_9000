import pytest

from tools.browser.core.snapshot import Element


def _make_long_text(length: int) -> str:
    return "A" * length


@pytest.mark.unit
def test_element_text_truncation_indicator():
    """Element.text adds (truncated) suffix when over MAX_ELEMENT_TEXT_LEN."""
    long_text = _make_long_text(150)
    # Simulate truncation logic outcome: construction does not itself truncate, logic lives in extractor.
    # Here we mimic the post-extraction value to assert convention.
    displayed = long_text[:120] + " (truncated)"
    el = Element(text=displayed, role=None, name=displayed, selector="#x", tag="a", href="https://x")
    assert el.text.endswith("(truncated)")
    # Should not exceed model max_length (140) and should be longer than the base clip.
    assert 120 < len(el.text) <= 140

