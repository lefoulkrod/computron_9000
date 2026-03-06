"""Unit tests for the ephemeral scratchpad tools."""

import pytest

from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.scratchpad.scratchpad import _scratchpad


@pytest.fixture(autouse=True)
def _fresh_scratchpad():
    """Ensure each test starts with no scratchpad state."""
    token = _scratchpad.set({})
    yield
    _scratchpad.reset(token)


@pytest.mark.unit
async def test_save_and_recall():
    """Save a key, recall it, and verify the value matches."""
    save_result = await save_to_scratchpad("color", "blue")
    assert save_result == {"status": "ok", "key": "color", "value": "blue"}

    recall_result = await recall_from_scratchpad("color")
    assert recall_result == {"status": "ok", "key": "color", "value": "blue"}


@pytest.mark.unit
async def test_recall_missing_key():
    """Recalling a key that was never saved returns not_found."""
    result = await recall_from_scratchpad("nonexistent")
    assert result == {"status": "not_found", "key": "nonexistent"}


@pytest.mark.unit
async def test_recall_all():
    """Save multiple keys, recall with key=None to get all items."""
    await save_to_scratchpad("a", "1")
    await save_to_scratchpad("b", "2")
    await save_to_scratchpad("c", "3")

    result = await recall_from_scratchpad(key=None)
    assert result == {"status": "ok", "items": {"a": "1", "b": "2", "c": "3"}}


@pytest.mark.unit
async def test_recall_all_empty():
    """Recalling all from an empty scratchpad returns an empty dict."""
    result = await recall_from_scratchpad(key=None)
    assert result == {"status": "ok", "items": {}}


@pytest.mark.unit
async def test_overwrite():
    """Saving the same key twice overwrites the previous value."""
    await save_to_scratchpad("x", "old")
    await save_to_scratchpad("x", "new")

    result = await recall_from_scratchpad("x")
    assert result == {"status": "ok", "key": "x", "value": "new"}


@pytest.mark.unit
async def test_lazy_init():
    """Scratchpad initializes lazily on first access without prior setup."""
    # Reset to no value at all (not even an empty dict)
    _scratchpad.set({})

    result = await save_to_scratchpad("k", "v")
    assert result["status"] == "ok"

    recall = await recall_from_scratchpad("k")
    assert recall["value"] == "v"
