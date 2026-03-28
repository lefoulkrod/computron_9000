"""Unit tests for the disk-backed scratchpad tools."""

from unittest.mock import patch

import pytest

from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.scratchpad.scratchpad import _cache


@pytest.fixture(autouse=True)
def _fresh_scratchpad(tmp_path):
    """Ensure each test starts with no scratchpad state and writes to tmp."""
    token = _cache.set({})
    with patch("tools.scratchpad.scratchpad.get_conversation_id", return_value="test-conv"), \
         patch("tools.scratchpad.scratchpad._scratchpad_path", return_value=tmp_path / "test-conv.json"):
        yield
    _cache.reset(token)


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
async def test_persists_to_disk(tmp_path):
    """Scratchpad writes should flush to a JSON file on disk."""
    disk_path = tmp_path / "disk-conv.json"
    with patch("tools.scratchpad.scratchpad._scratchpad_path", return_value=disk_path):
        await save_to_scratchpad("k", "v")

    assert disk_path.exists()
    import json
    data = json.loads(disk_path.read_text())
    assert data["k"] == "v"
