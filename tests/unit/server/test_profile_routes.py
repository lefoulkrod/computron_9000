"""Tests for server._profile_routes HTTP handlers.

Focused on the disable-default-agent rule (400 response) and the
``?include_disabled=true`` query parameter on the list endpoint.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents._agent_profiles import AgentProfile, save_agent_profile
from server._profile_routes import handle_list_profiles, handle_update_profile


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point profiles and settings at temp paths."""
    monkeypatch.setattr(
        "agents._agent_profiles._profiles_dir",
        lambda: tmp_path / "agent_profiles",
    )
    monkeypatch.setattr(
        "settings._settings_path",
        lambda: tmp_path / "settings.json",
    )


def _make_request(*, match_info=None, json_body=None, query=None):
    """Build a minimal aiohttp.web.Request-ish double."""
    req = MagicMock()
    req.match_info = match_info or {}
    req.query = query or {}
    if json_body is not None:
        req.json = AsyncMock(return_value=json_body)
    return req


@pytest.mark.unit
class TestListProfilesFilter:
    """Query-param filtering on GET /api/profiles."""

    async def test_default_hides_disabled(self):
        """Without ?include_disabled, only enabled profiles are returned."""
        save_agent_profile(AgentProfile(id="on", name="On", model="m", enabled=True))
        save_agent_profile(AgentProfile(id="off", name="Off", model="m", enabled=False))

        req = _make_request(query={})
        resp = await handle_list_profiles(req)
        body = json.loads(resp.body)
        ids = {p["id"] for p in body}
        assert "on" in ids
        assert "off" not in ids

    async def test_include_disabled_returns_all(self):
        """?include_disabled=true returns every profile."""
        save_agent_profile(AgentProfile(id="on", name="On", model="m", enabled=True))
        save_agent_profile(AgentProfile(id="off", name="Off", model="m", enabled=False))

        req = _make_request(query={"include_disabled": "true"})
        resp = await handle_list_profiles(req)
        body = json.loads(resp.body)
        ids = {p["id"] for p in body}
        assert ids == {"on", "off"}


@pytest.mark.unit
class TestDisableDefaultRule:
    """PUT /api/profiles/{id} refuses to disable whatever is the default."""

    async def test_disable_non_default_is_allowed(self):
        """Disabling a profile that isn't the default succeeds."""
        from settings import save_settings
        save_settings({"default_agent": "computron"})
        save_agent_profile(AgentProfile(id="computron", name="C", model="m"))
        save_agent_profile(AgentProfile(id="other", name="Other", model="m"))

        req = _make_request(
            match_info={"id": "other"},
            json_body={"id": "other", "name": "Other", "model": "m", "enabled": False},
        )
        resp = await handle_update_profile(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["enabled"] is False

    async def test_disable_default_is_rejected(self):
        """Disabling the currently-set default_agent returns 400."""
        from settings import save_settings
        save_settings({"default_agent": "computron"})
        save_agent_profile(AgentProfile(id="computron", name="Computron", model="m"))

        req = _make_request(
            match_info={"id": "computron"},
            json_body={"id": "computron", "name": "Computron", "model": "m", "enabled": False},
        )
        resp = await handle_update_profile(req)
        assert resp.status == 400
        body = json.loads(resp.body)
        assert body["error"] == "default_agent_cannot_be_disabled"
        assert "default" in body["message"].lower()

    async def test_enable_default_is_allowed(self):
        """Setting enabled=True on the default is fine (no-op)."""
        from settings import save_settings
        save_settings({"default_agent": "computron"})
        save_agent_profile(AgentProfile(id="computron", name="Computron", model="m"))

        req = _make_request(
            match_info={"id": "computron"},
            json_body={"id": "computron", "name": "Computron", "model": "m", "enabled": True},
        )
        resp = await handle_update_profile(req)
        assert resp.status == 200

    async def test_updating_other_fields_on_default_is_allowed(self):
        """Changing name/description on the default doesn't trigger the rule."""
        from settings import save_settings
        save_settings({"default_agent": "computron"})
        save_agent_profile(AgentProfile(id="computron", name="C", model="m"))

        req = _make_request(
            match_info={"id": "computron"},
            json_body={"id": "computron", "name": "Renamed", "model": "m"},
        )
        resp = await handle_update_profile(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["name"] == "Renamed"

    async def test_disable_default_after_reassignment_is_allowed(self):
        """Once default moves off a profile, that profile can be disabled."""
        from settings import save_settings
        save_settings({"default_agent": "computron"})
        save_agent_profile(AgentProfile(id="computron", name="C", model="m"))
        save_agent_profile(AgentProfile(id="other", name="Other", model="m"))

        # Move default to "other", then disable computron
        save_settings({"default_agent": "other"})
        req = _make_request(
            match_info={"id": "computron"},
            json_body={"id": "computron", "name": "C", "model": "m", "enabled": False},
        )
        resp = await handle_update_profile(req)
        assert resp.status == 200
