from unittest.mock import AsyncMock, patch

import pytest

from tools.web.get_webpage import GetWebpageError, get_webpage_substring


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_webpage_substring_returns_correct_slice():
    """
    Unit test: get_webpage_substring returns the correct substring for valid indices.
    """
    fake_text = "Hello, this is a test web page."
    fake_url = "https://example.com"
    with patch(
        "tools.web.get_webpage.get_webpage",
        new=AsyncMock(
            return_value=type("ReducedWebpage", (), {"page_text": fake_text})()
        ),
    ):
        result = await get_webpage_substring(fake_url, 7, 11)
        assert result == "this"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_webpage_substring_invalid_indices_raises_valueerror():
    """
    Unit test: get_webpage_substring raises ValueError for invalid indices.
    """
    fake_text = "Short text"
    fake_url = "https://example.com"
    with (
        patch(
            "tools.web.get_webpage.get_webpage",
            new=AsyncMock(
                return_value=type("ReducedWebpage", (), {"page_text": fake_text})()
            ),
        ),
        pytest.raises(GetWebpageError),
    ):
        await get_webpage_substring(fake_url, 5, 100)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_webpage_substring_handles_getwebpageerror():
    """
    Unit test: get_webpage_substring raises GetWebpageError if get_webpage fails.
    """
    fake_url = "https://example.com"
    with (
        patch(
            "tools.web.get_webpage.get_webpage",
            new=AsyncMock(side_effect=Exception("fail")),
        ),
        pytest.raises(GetWebpageError),
    ):
        await get_webpage_substring(fake_url, 0, 1)
