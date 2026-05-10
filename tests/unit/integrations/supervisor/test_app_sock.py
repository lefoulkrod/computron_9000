"""Tests for supervisor app-socket wire serialization."""

from unittest.mock import MagicMock

import pytest

from integrations.permissions import Access, Capability
from integrations.supervisor._app_sock import _record_to_dict


@pytest.mark.unit
def test_record_to_dict_includes_capabilities() -> None:
    """The list response must include a capabilities array derived from max_access."""
    record = MagicMock()
    record.meta.id = "llm_openai"
    record.meta.slug = "llm_openai"
    record.meta.label = "OpenAI"
    record.meta.permissions = {}
    record.max_access = {Capability.LLM_PROXY: Access.READ_WRITE}
    record.state = "running"
    record.broker.socket_path = "/run/cvault/llm_openai.sock"

    result = _record_to_dict(record)

    assert "capabilities" in result
    assert "llm_proxy" in result["capabilities"]


@pytest.mark.unit
def test_record_to_dict_capabilities_sorted() -> None:
    """Capabilities are sorted alphabetically for stable wire output."""
    record = MagicMock()
    record.meta.id = "icloud_alice"
    record.meta.slug = "icloud"
    record.meta.label = "iCloud"
    record.meta.permissions = {
        Capability.EMAIL: Access.READ_WRITE,
        Capability.CALENDAR: Access.READ,
    }
    record.max_access = {
        Capability.EMAIL: Access.READ_WRITE,
        Capability.CALENDAR: Access.READ_WRITE,
    }
    record.state = "running"
    record.broker.socket_path = "/run/cvault/icloud_alice.sock"

    result = _record_to_dict(record)

    assert result["capabilities"] == ["calendar", "email"]
