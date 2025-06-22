import logging
import re
import pytest
from tools.web.get_webpage import _reduce_webpage_context

logger = logging.getLogger(__name__)

def test_reduce_webpage_context_removes_scripts_and_preserves_links():
    """
    Test that _reduce_webpage_context removes scripts/styles and preserves links and structure.
    """
    html = '''
    <html><head><title>Test</title><script>var x=1;</script></head>
    <body>
        <div>
            <a href="https://example.com" style="color:red;">Example</a>
            <img src="img.png" style="width:100px;" alt="desc">
            <script>alert('hi');</script>
            <span>Keep me</span>
        </div>
    </body></html>
    '''
    reduced = _reduce_webpage_context(html)
    assert '<script>' not in reduced
    assert '<a href="https://example.com"' in reduced
    assert 'style=' not in reduced
    # Check <img> tag with both src and alt, regardless of order
    assert '<img' in reduced and 'src="img.png"' in reduced and 'alt="desc"' in reduced
    assert '<span>Keep me</span>' in reduced or 'Keep me' in reduced
    assert '<div>' in reduced or '<div' not in html  # structure preserved

def test_reduce_webpage_context_removes_empty_tags():
    """
    Test that empty tags (except <a> and <img>) are removed.
    """
    html = '<div></div><span></span><a href="/foo"></a><img src="foo.png">'
    reduced = _reduce_webpage_context(html)
    assert '<div' not in reduced
    assert '<span' not in reduced
    assert '<a href="/foo"></a>' in reduced
    assert '<img src="foo.png"' in reduced

def test_reduce_webpage_context_removes_head_and_html_elements():
    """
    Test that <head> and <html> elements are removed from the reduced HTML.
    """
    html = '''
    <html>
      <head><title>Should be gone</title></head>
      <body><div>Content</div></body>
    </html>
    '''
    reduced = _reduce_webpage_context(html)
    assert '<head' not in reduced
    assert '<html' not in reduced
    assert 'Should be gone' not in reduced
    assert '<div>Content</div>' in reduced or 'Content' in reduced
