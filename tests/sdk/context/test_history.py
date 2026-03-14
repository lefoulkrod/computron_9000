"""Tests for ConversationHistory."""

import pytest

from sdk.context import ConversationHistory


@pytest.mark.unit
class TestConversationHistory:
    """Tests for the ConversationHistory class."""

    def test_empty_init(self):
        h = ConversationHistory()
        assert len(h) == 0
        assert h.messages == []

    def test_init_with_messages(self):
        msgs = [{"role": "system", "content": "hi"}]
        h = ConversationHistory(msgs)
        assert len(h) == 1
        # Original list should not be mutated
        msgs.append({"role": "user", "content": "yo"})
        assert len(h) == 1

    def test_append(self):
        h = ConversationHistory()
        h.append({"role": "user", "content": "hello"})
        assert len(h) == 1
        assert h.messages[0]["content"] == "hello"

    def test_messages_returns_copy(self):
        """The messages property should return a copy, not the internal list."""
        h = ConversationHistory()
        h.append({"role": "user", "content": "a"})
        msgs = h.messages
        msgs.append({"role": "user", "content": "b"})
        assert len(h) == 1

    def test_clear(self):
        h = ConversationHistory([{"role": "user", "content": "a"}])
        h.clear()
        assert len(h) == 0

    def test_iter(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
        ]
        h = ConversationHistory(msgs)
        assert list(h) == msgs

    def test_system_message_present(self):
        h = ConversationHistory([{"role": "system", "content": "sys"}])
        assert h.system_message == {"role": "system", "content": "sys"}

    def test_system_message_absent(self):
        h = ConversationHistory([{"role": "user", "content": "usr"}])
        assert h.system_message is None

    def test_non_system_messages(self):
        h = ConversationHistory([
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ])
        assert len(h.non_system_messages) == 2
        assert h.non_system_messages[0]["content"] == "a"

    def test_non_system_messages_no_system(self):
        h = ConversationHistory([{"role": "user", "content": "a"}])
        assert len(h.non_system_messages) == 1

    def test_set_system_message_replaces(self):
        h = ConversationHistory([{"role": "system", "content": "old"}])
        h.set_system_message("new")
        assert h.system_message == {"role": "system", "content": "new"}
        assert len(h) == 1

    def test_set_system_message_inserts(self):
        h = ConversationHistory([{"role": "user", "content": "a"}])
        h.set_system_message("sys")
        assert len(h) == 2
        assert h.system_message == {"role": "system", "content": "sys"}
        assert h.messages[1]["content"] == "a"

    def test_drop_range(self):
        h = ConversationHistory([
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ])
        h.drop_range(1, 3)
        assert len(h) == 2
        assert h.messages[0]["content"] == "sys"
        assert h.messages[1]["content"] == "c"

    def test_drop_range_invalid(self):
        h = ConversationHistory([{"role": "user", "content": "a"}])
        with pytest.raises(IndexError):
            h.drop_range(0, 5)

    def test_insert(self):
        h = ConversationHistory([
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "a"},
        ])
        h.insert(1, {"role": "user", "content": "inserted"})
        assert len(h) == 3
        assert h.messages[1]["content"] == "inserted"
        assert h.messages[2]["content"] == "a"

    def test_insert_at_end(self):
        h = ConversationHistory([{"role": "user", "content": "a"}])
        h.insert(1, {"role": "user", "content": "b"})
        assert len(h) == 2
        assert h.messages[1]["content"] == "b"

    def test_insert_out_of_bounds(self):
        h = ConversationHistory([{"role": "user", "content": "a"}])
        with pytest.raises(IndexError):
            h.insert(5, {"role": "user", "content": "b"})

    def test_repr(self):
        h = ConversationHistory([{"role": "user", "content": "a"}])
        assert "len=1" in repr(h)
