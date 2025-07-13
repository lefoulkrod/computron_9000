import pytest

from tools.web.html_find_elements import HtmlElementResult, html_find_elements


@pytest.mark.asyncio
@pytest.mark.unit
async def test_html_find_elements_basic():
    """
    Test finding <a> tags with and without text filtering.
    """
    html = """
    <html>
        <body>
            <a href="https://example.com">Click Here</a>
            <a href="https://example.com/2">Other Link</a>
        </body>
    </html>
    """
    # Find all <a> tags with a string parameter
    results = await html_find_elements(html, selectors="a")
    assert len(results) == 2
    assert all(isinstance(r, HtmlElementResult) for r in results)

    # Find <a> tags with text "Click Here"
    results = await html_find_elements(html, selectors="a", text="Click Here")
    assert len(results) == 1
    assert "Click Here" in results[0].html_element


@pytest.mark.asyncio
@pytest.mark.unit
async def test_html_find_elements_case_insensitive():
    """
    Test that html_find_elements matches text case-insensitively.
    """
    html = """
    <html>
        <body>
            <a href="https://example.com">Click Here</a>
            <a href="https://example.com/2">other link</a>
        </body>
    </html>
    """
    # Search with different casing
    results = await html_find_elements(html, selectors="a", text="click here")
    assert len(results) == 1
    assert "Click Here" in results[0].html_element

    results = await html_find_elements(html, selectors="a", text="OTHER LINK")
    assert len(results) == 1
    assert "other link" in results[0].html_element


@pytest.mark.asyncio
@pytest.mark.unit
async def test_html_find_elements_list_tags():
    """
    Test finding elements with a list of tags.
    """
    html = """
    <html>
        <body>
            <a href="https://example.com">Click Here</a>
            <span class="highlight">Important</span>
            <div class="container">Container</div>
            <p>A paragraph</p>
        </body>
    </html>
    """
    # Find multiple tag types
    results = await html_find_elements(html, selectors=["a", "span"])
    assert len(results) == 2
    assert any("Click Here" in r.html_element for r in results)
    assert any("Important" in r.html_element for r in results)

    # Find multiple tag types with text filter
    results = await html_find_elements(html, selectors=["a", "p"], text="paragraph")
    assert len(results) == 1
    assert "A paragraph" in results[0].html_element


@pytest.mark.asyncio
@pytest.mark.unit
async def test_html_find_elements_css_selectors():
    """
    Test finding elements using CSS selectors.
    """
    html = """
    <html>
        <body>
            <a href="https://example.com" class="primary">Primary Link</a>
            <a href="https://example.com/2" class="secondary">Secondary Link</a>
            <span class="highlight">Highlighted Text</span>
            <div id="container">Container Div</div>
        </body>
    </html>
    """
    # Find by class
    results = await html_find_elements(html, selectors=".primary")
    assert len(results) == 1
    assert "Primary Link" in results[0].html_element

    # Find by id
    results = await html_find_elements(html, selectors="#container")
    assert len(results) == 1
    assert "Container Div" in results[0].html_element

    # Find with combined selector
    results = await html_find_elements(html, selectors="a.secondary")
    assert len(results) == 1
    assert "Secondary Link" in results[0].html_element

    # Find with multiple CSS selectors
    results = await html_find_elements(html, selectors=[".primary", "#container"])
    assert len(results) == 2
    assert any("Primary Link" in r.html_element for r in results)
    assert any("Container Div" in r.html_element for r in results)

    # Find with CSS selector and text filter
    results = await html_find_elements(html, selectors=".highlight", text="highlighted")
    assert len(results) == 1
    assert "Highlighted Text" in results[0].html_element
