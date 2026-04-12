"""Tests for agents._agent_profiles."""

import json

import pytest

from agents._agent_profiles import (
    AgentProfile,
    build_llm_options,
    delete_agent_profile,
    duplicate_agent_profile,
    get_agent_profile,
    get_default_profile,
    list_agent_profiles,
    save_agent_profile,
    set_model_on_profiles,
    _profiles_dir,
)


@pytest.fixture(autouse=True)
def _isolate_profiles(tmp_path, monkeypatch):
    """Point profiles at a temp directory for each test."""
    monkeypatch.setattr(
        "agents._agent_profiles._profiles_dir",
        lambda: tmp_path / "agent_profiles",
    )


def _make_profile(**overrides):
    defaults = {
        "id": "test",
        "name": "Test",
        "model": "test-model:7b",
        "system_prompt": "You are a test agent.",
    }
    defaults.update(overrides)
    return AgentProfile(**defaults)


@pytest.mark.unit
class TestAgentProfileModel:
    """AgentProfile Pydantic model validation."""

    def test_minimal_profile(self):
        """Profile with just required fields."""
        p = AgentProfile(id="x", name="X", model="m")
        assert p.id == "x"
        assert p.skills == []
        assert p.temperature is None
        assert p.think is None

    def test_full_profile(self):
        """Profile with all fields set."""
        p = AgentProfile(
            id="full", name="Full", model="m",
            description="desc",
            system_prompt="prompt", skills=["coder", "browser"],
            temperature=0.5, top_k=40, top_p=0.9,
            repeat_penalty=1.1, num_predict=1000,
            think=True, num_ctx=32000, max_iterations=10,
        )
        assert p.skills == ["coder", "browser"]
        assert p.temperature == 0.5
        assert p.num_ctx == 32000

    def test_roundtrip_serialization(self):
        """Profile survives JSON round-trip."""
        p = _make_profile(skills=["coder"], temperature=0.3)
        data = json.loads(json.dumps(p.model_dump()))
        p2 = AgentProfile.model_validate(data)
        assert p2.id == p.id
        assert p2.skills == p.skills
        assert p2.temperature == p.temperature


@pytest.mark.unit
class TestProfileCRUD:
    """Save, load, list, delete operations."""

    def test_save_and_get(self):
        """Saved profile can be retrieved by ID."""
        p = _make_profile()
        save_agent_profile(p)
        loaded = get_agent_profile("test")
        assert loaded is not None
        assert loaded.name == "Test"
        assert loaded.model == "test-model:7b"

    def test_get_nonexistent(self):
        """Missing profile returns None."""
        assert get_agent_profile("nope") is None

    def test_list_profiles_empty(self):
        """Empty directory returns empty list."""
        assert list_agent_profiles() == []

    def test_list_profiles_sorted(self):
        """Profiles are sorted by name, Computron first."""
        save_agent_profile(_make_profile(id="zebra", name="Zebra"))
        save_agent_profile(_make_profile(id="computron", name="Computron"))
        save_agent_profile(_make_profile(id="alpha", name="Alpha"))
        result = list_agent_profiles()
        names = [p.name for p in result]
        assert names == ["Computron", "Alpha", "Zebra"]

    def test_delete_profile(self):
        """Deleted profile is gone."""
        save_agent_profile(_make_profile())
        assert delete_agent_profile("test") is True
        assert get_agent_profile("test") is None

    def test_delete_nonexistent(self):
        """Deleting missing profile returns False."""
        assert delete_agent_profile("nope") is False

    def test_save_overwrites(self):
        """Saving with same ID overwrites."""
        save_agent_profile(_make_profile(name="V1"))
        save_agent_profile(_make_profile(name="V2"))
        loaded = get_agent_profile("test")
        assert loaded.name == "V2"


@pytest.mark.unit
class TestDuplicate:
    """Profile duplication."""

    def test_duplicate_creates_new_id(self):
        """Duplicate gets a new ID."""
        save_agent_profile(_make_profile())
        clone = duplicate_agent_profile("test")
        assert clone.id != "test"
        assert clone.name == "Test (copy)"
        assert clone.model == "test-model:7b"

    def test_duplicate_custom_name(self):
        """Duplicate with custom name."""
        save_agent_profile(_make_profile())
        clone = duplicate_agent_profile("test", new_name="My Clone")
        assert clone.name == "My Clone"

    def test_duplicate_nonexistent_raises(self):
        """Duplicating missing profile raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            duplicate_agent_profile("nope")

    def test_duplicate_is_independent(self):
        """Changes to duplicate don't affect original."""
        save_agent_profile(_make_profile())
        clone = duplicate_agent_profile("test")
        clone = clone.model_copy(update={"name": "Changed"})
        save_agent_profile(clone)
        original = get_agent_profile("test")
        assert original.name == "Test"


@pytest.mark.unit
class TestBuildLLMOptions:
    """Converting profiles to LLMOptions."""

    def test_basic_conversion(self):
        """Profile fields map to LLMOptions."""
        p = _make_profile(temperature=0.5, top_k=40, think=True, num_ctx=16000)
        opts = build_llm_options(p)
        assert opts.model == "test-model:7b"
        assert opts.temperature == 0.5
        assert opts.top_k == 40
        assert opts.think is True
        assert opts.num_ctx == 16000

    def test_none_fields_stay_none(self):
        """Unset profile fields remain None in options."""
        p = _make_profile()
        opts = build_llm_options(p)
        assert opts.temperature is None
        assert opts.top_k is None
        assert opts.max_iterations is None

    def test_model_inheritance(self):
        """Profile with no model inherits from Computron."""
        save_agent_profile(_make_profile(id="computron", name="Computron", model="big-model:70b"))
        p = _make_profile(id="child", model="")
        opts = build_llm_options(p)
        assert opts.model == "big-model:70b"

    def test_computron_no_inheritance(self):
        """Computron itself doesn't try to inherit."""
        p = _make_profile(id="computron", model="my-model:32b")
        opts = build_llm_options(p)
        assert opts.model == "my-model:32b"


@pytest.mark.unit
class TestSetModelOnProfiles:
    """Bulk model setting for setup wizard."""

    def test_sets_model_on_empty_profiles(self):
        """Profiles with no model get the new model."""
        save_agent_profile(_make_profile(id="a", name="A", model=""))
        save_agent_profile(_make_profile(id="b", name="B", model=""))
        set_model_on_profiles("new-model:32b")
        assert get_agent_profile("a").model == "new-model:32b"
        assert get_agent_profile("b").model == "new-model:32b"

    def test_skips_profiles_with_model(self):
        """Profiles that already have a model are untouched."""
        save_agent_profile(_make_profile(id="a", name="A", model="existing:7b"))
        save_agent_profile(_make_profile(id="b", name="B", model=""))
        set_model_on_profiles("new-model:32b")
        assert get_agent_profile("a").model == "existing:7b"
        assert get_agent_profile("b").model == "new-model:32b"


@pytest.mark.unit
class TestGetDefaultProfile:
    """Default profile retrieval."""

    def test_returns_computron(self):
        """Returns the Computron profile."""
        save_agent_profile(_make_profile(id="computron", name="Computron"))
        p = get_default_profile()
        assert p.id == "computron"

    def test_raises_when_missing(self):
        """Raises RuntimeError if Computron not found."""
        with pytest.raises(RuntimeError, match="not found"):
            get_default_profile()


@pytest.mark.unit
class TestLegacySystemFieldStripped:
    """Legacy 'system' field is stripped on load."""

    def test_system_field_ignored(self, tmp_path, monkeypatch):
        """Old profiles with 'system' field load without error."""
        monkeypatch.setattr(
            "agents._agent_profiles._profiles_dir",
            lambda: tmp_path / "agent_profiles",
        )
        d = tmp_path / "agent_profiles"
        d.mkdir(parents=True)
        data = {"id": "old", "name": "Old", "model": "m", "system": True}
        (d / "old.json").write_text(json.dumps(data))
        p = get_agent_profile("old")
        assert p is not None
        assert p.id == "old"
        assert not hasattr(p, "system")
