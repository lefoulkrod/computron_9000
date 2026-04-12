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

from agents.types import LLMOptions
from config import load_config

logger = logging.getLogger(__name__)

_PROFILES_SUBDIR = "agent_profiles"

COMPUTRON_ID = "computron"


class AgentProfile(BaseModel):
    """A reusable agent configuration."""

    id: str
    name: str
    description: str = ""
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


def list_agent_profiles() -> list[AgentProfile]:
    """Return all agent profiles, Computron first."""
    profiles = _load_all()
    result: list[AgentProfile] = []
    if COMPUTRON_ID in profiles:
        result.append(profiles.pop(COMPUTRON_ID))
    result.extend(sorted(profiles.values(), key=lambda p: p.name))
    return result


def get_agent_profile(profile_id: str) -> AgentProfile | None:
    """Look up a profile by ID."""
    profiles = _load_all()
    return profiles.get(profile_id)


def get_default_profile() -> AgentProfile:
    """Return the Computron profile."""
    profile = get_agent_profile(COMPUTRON_ID)
    if profile is None:
        msg = "Computron profile not found — run setup wizard"
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


def build_llm_options(profile: AgentProfile) -> LLMOptions:
    """Convert an AgentProfile to LLMOptions for the turn machinery.

    If the profile has no model set, inherits from the Computron profile.
    """
    model = profile.model
    if not model and profile.id != COMPUTRON_ID:
        default = get_agent_profile(COMPUTRON_ID)
        if default:
            model = default.model
    return LLMOptions(
        model=model,
        think=profile.think,
        num_ctx=profile.num_ctx,
        num_predict=profile.num_predict,
        temperature=profile.temperature,
        top_k=profile.top_k,
        top_p=profile.top_p,
        repeat_penalty=profile.repeat_penalty,
        max_iterations=profile.max_iterations,
    )


__all__ = [
    "COMPUTRON_ID",
    "AgentProfile",
    "build_llm_options",
    "delete_agent_profile",
    "duplicate_agent_profile",
    "get_agent_profile",
    "get_default_profile",
    "list_agent_profiles",
    "save_agent_profile",
    "set_model_on_profiles",
]
