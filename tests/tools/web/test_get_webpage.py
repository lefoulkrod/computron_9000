import logging

import pytest

from tools.web.get_webpage import _reduce_webpage_context
from tools.web.types import ReducedWebpage

logger = logging.getLogger(__name__)


@pytest.mark.unit
def test_reduce_webpage_context_extracts_links_and_text():
    """
    Test that _reduce_webpage_context extracts all links and returns only text content.
    """
    html = """
    <html><head><title>Test</title><script>var x=1;</script></head>
    <body>
        <div>
            <a href="https://example.com" style="color:red;">Example</a>
            <a href="/foo">Foo Link</a>
            <img src="img.png" style="width:100px;" alt="desc">
            <script>alert('hi');</script>
            <span>Keep me</span>
        </div>
    </body></html>
    """
    reduced = _reduce_webpage_context(html)
    assert isinstance(reduced, ReducedWebpage)
    assert hasattr(reduced, "page_text")
    assert hasattr(reduced, "links")
    # Should not contain any HTML tags
    assert "<" not in reduced.page_text and ">" not in reduced.page_text
    # Should contain visible text
    assert "Example" in reduced.page_text
    assert "Keep me" in reduced.page_text
    # Links should be extracted in order
    assert len(reduced.links) == 2
    assert reduced.links[0].href == "https://example.com"
    assert reduced.links[0].text == "Example"
    assert reduced.links[1].href == "/foo"
    assert reduced.links[1].text == "Foo Link"


@pytest.mark.unit
def test_reduce_webpage_context_handles_empty_and_head():
    """
    Test that empty tags and <head>/<html> elements are ignored in text output.
    """
    html = """<html><head><title>Should be gone</title></head><body><div>Content</div></body></html>"""
    reduced = _reduce_webpage_context(html)
    assert "Should be gone" not in reduced.page_text
    assert "Content" in reduced.page_text
    assert len(reduced.links) == 0
