import pytest
import asyncio

from tools.web.html_find_elements import html_find_elements, HtmlElementResult

@pytest.mark.asyncio
async def test_html_find_elements_basic():
    """
    Test finding <a> tags with and without text filtering.
    """
    html = '''
    <html>
        <body>
            <a href="https://example.com">Click Here</a>
            <a href="https://example.com/2">Other Link</a>
        </body>
    </html>
    '''
    # Find all <a> tags
    results = await html_find_elements(html, tag="a")
    assert len(results) == 2
    assert all(isinstance(r, HtmlElementResult) for r in results)

    # Find <a> tags with text "Click Here"
    results = await html_find_elements(html, tag="a", text="Click Here")
    assert len(results) == 1
    assert "Click Here" in results[0].html_element

@pytest.mark.asyncio
async def test_html_find_elements_case_insensitive():
    """
    Test that html_find_elements matches text case-insensitively.
    """
    html = '''
    <html>
        <body>
            <a href="https://example.com">Click Here</a>
            <a href="https://example.com/2">other link</a>
        </body>
    </html>
    '''
    # Search with different casing
    results = await html_find_elements(html, tag="a", text="click here")
    assert len(results) == 1
    assert "Click Here" in results[0].html_element

    results = await html_find_elements(html, tag="a", text="OTHER LINK")
    assert len(results) == 1
    assert "other link" in results[0].html_element
