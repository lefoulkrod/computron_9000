"""Agent profile registry and persistence.

An AgentProfile bundles model, system prompt, skills, and inference
parameters into a reusable configuration. Profiles are stored as JSON
files in the state folder.
"""

import json
import logging
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from config import load_config
from settings import load_settings

logger = logging.getLogger(__name__)

_PROFILES_SUBDIR = "agent_profiles"

COMPUTRON_ID = "computron"


class AgentProfile(BaseModel):
    """A reusable agent configuration."""

    id: str
    name: str
    description: str = ""
    enabled: bool = True
    system_prompt: str = ""
    model: str = ""
    skills: list[str] = Field(default_factory=list)
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    repeat_penalty: float | None = None
    num_predict: int | None = None
    think: bool | None = None
    num_ctx: int | None = None
    max_iterations: int | None = None


def _profiles_dir() -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / _PROFILES_SUBDIR


def _load_all() -> dict[str, AgentProfile]:
    """Load all profiles from disk."""
    profiles: dict[str, AgentProfile] = {}
    d = _profiles_dir()
    if not d.is_dir():
        return profiles
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            # Strip legacy 'system' field if present
            data.pop("system", None)
            profile = AgentProfile.model_validate(data)
            profiles[profile.id] = profile
        except Exception:
            logger.warning("Failed to load agent profile %s", f.name)
    return profiles


def list_agent_profiles(include_disabled: bool = False) -> list[AgentProfile]:
    """Return agent profiles.

    Ordering: Computron first (if present and not filtered out), then the
    remaining profiles sorted by name.

    Args:
        include_disabled: If False (default), profiles with ``enabled=False``
            are filtered out. Callers that need every profile (e.g. the
            profile-management UI) should pass True.
    """
    profiles = _load_all()
    result: list[AgentProfile] = []
    if COMPUTRON_ID in profiles:
        result.append(profiles.pop(COMPUTRON_ID))
    result.extend(sorted(profiles.values(), key=lambda p: p.name))
    if not include_disabled:
        result = [p for p in result if p.enabled]
    return result


def get_agent_profile(profile_id: str) -> AgentProfile | None:
    """Look up a profile by ID."""
    profiles = _load_all()
    return profiles.get(profile_id)


def get_default_profile() -> AgentProfile:
    """Return the profile configured as the app-wide default agent."""
    default_id = load_settings()["default_agent"]
    profile = get_agent_profile(default_id)
    if profile is None:
        msg = f"Default agent profile '{default_id}' not found — run setup wizard"
        raise RuntimeError(msg)
    return profile


def save_agent_profile(profile: AgentProfile) -> AgentProfile:
    """Save a profile to disk."""
    d = _profiles_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{profile.id}.json"
    path.write_text(json.dumps(profile.model_dump(), indent=2))
    return profile


def set_model_on_profiles(model: str) -> None:
    """Set the model on all profiles that have no model. Used by setup wizard."""
    d = _profiles_dir()
    d.mkdir(parents=True, exist_ok=True)
    for profile in _load_all().values():
        if not profile.model:
            updated = profile.model_copy(update={"model": model})
            path = d / f"{updated.id}.json"
            path.write_text(json.dumps(updated.model_dump(), indent=2))
            logger.info("Set model '%s' on profile '%s'", model, profile.id)


def delete_agent_profile(profile_id: str) -> bool:
    """Delete a profile. Returns False if not found."""
    profile = get_agent_profile(profile_id)
    if profile is None:
        return False
    path = _profiles_dir() / f"{profile_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def duplicate_agent_profile(profile_id: str, new_name: str | None = None) -> AgentProfile:
    """Duplicate a profile with a new ID and name."""
    source = get_agent_profile(profile_id)
    if source is None:
        msg = f"Profile '{profile_id}' not found"
        raise ValueError(msg)
    new_id = uuid4().hex[:12]
    name = new_name or f"{source.name} (copy)"
    clone = source.model_copy(update={"id": new_id, "name": name})
    return save_agent_profile(clone)


__all__ = [
    "COMPUTRON_ID",
    "AgentProfile",
    "delete_agent_profile",
    "duplicate_agent_profile",
    "get_agent_profile",
    "get_default_profile",
    "list_agent_profiles",
    "save_agent_profile",
    "set_model_on_profiles",
]
