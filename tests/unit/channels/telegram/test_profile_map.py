"""Tests for channels.telegram._profile_map.ProfileMap."""

import pytest

from channels.telegram._profile_map import ProfileMap


@pytest.mark.unit
class TestProfileMap:

    def test_unknown_chat_returns_none(self):
        pmap = ProfileMap()
        assert pmap.get(404) is None

    def test_set_then_get(self):
        pmap = ProfileMap()
        pmap.set(7, "code_expert")
        assert pmap.get(7) == "code_expert"

    def test_set_overwrites_previous_choice(self):
        pmap = ProfileMap()
        pmap.set(7, "first")
        pmap.set(7, "second")
        assert pmap.get(7) == "second"

    def test_clear_drops_choice(self):
        pmap = ProfileMap()
        pmap.set(7, "x")
        pmap.clear(7)
        assert pmap.get(7) is None

    def test_clear_unknown_chat_is_a_no_op(self):
        pmap = ProfileMap()
        pmap.clear(404)  # should not raise

    def test_independent_chats(self):
        pmap = ProfileMap()
        pmap.set(1, "a")
        pmap.set(2, "b")
        assert pmap.get(1) == "a"
        assert pmap.get(2) == "b"
