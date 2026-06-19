"""Tests for channels.telegram._state.ConversationMap."""

import pytest

from channels.telegram._state import ConversationMap


@pytest.mark.unit
class TestConversationMap:

    def test_get_creates_default_conv_id_on_first_access(self):
        cmap = ConversationMap()
        cid = cmap.get(12345)
        assert cid == "telegram_12345"

    def test_get_is_idempotent_for_same_chat(self):
        cmap = ConversationMap()
        first = cmap.get(7)
        second = cmap.get(7)
        assert first == second

    def test_different_chats_get_distinct_ids(self):
        cmap = ConversationMap()
        a = cmap.get(1)
        b = cmap.get(2)
        assert a != b

    def test_reset_assigns_new_unique_id_with_chat_id_prefix(self):
        cmap = ConversationMap()
        original = cmap.get(42)
        reset = cmap.reset(42)

        assert reset != original
        # Still keyed back to the chat — the prefix preserves traceability.
        assert reset.startswith("telegram_42_")
        # Subsequent get returns the reset id, not the default.
        assert cmap.get(42) == reset

    def test_reset_is_unique_across_resets_on_same_chat(self):
        cmap = ConversationMap()
        cmap.get(99)
        first_reset = cmap.reset(99)
        second_reset = cmap.reset(99)
        assert first_reset != second_reset

    def test_conversation_id_for_returns_none_when_unknown(self):
        cmap = ConversationMap()
        assert cmap.conversation_id_for(404) is None

    def test_conversation_id_for_returns_current_id_without_creating(self):
        cmap = ConversationMap()
        assert cmap.conversation_id_for(8) is None  # not created
        cmap.get(8)
        assert cmap.conversation_id_for(8) == "telegram_8"

    def test_conversation_id_for_reflects_reset(self):
        cmap = ConversationMap()
        cmap.get(15)
        new = cmap.reset(15)
        assert cmap.conversation_id_for(15) == new

    def test_set_binds_chat_to_existing_id(self):
        cmap = ConversationMap()
        cmap.set(42, "telegram_42_abc123")
        assert cmap.get(42) == "telegram_42_abc123"

    def test_set_overwrites_any_previous_binding(self):
        cmap = ConversationMap()
        cmap.get(42)                              # default id
        cmap.reset(42)                            # uuid id
        cmap.set(42, "telegram_42_explicit")      # explicit override
        assert cmap.conversation_id_for(42) == "telegram_42_explicit"
