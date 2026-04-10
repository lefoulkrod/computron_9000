"""Inference profile registry.

Profiles are named presets for LLM inference parameters (temperature, top_k,
etc.) that can be attached to agents or goal tasks. Built-in profiles are
always available; user-created profiles are persisted to disk.
"""

import json
import logging
from pathlib import Path

from agents.types import InferenceProfile
from config import load_config

logger = logging.getLogger(__name__)

_PROFILE_REGISTRY: dict[str, InferenceProfile] = {}
_loaded = False

# ── Built-in profiles ──────────────────────────────────────────────────────

_BUILTINS: list[InferenceProfile] = [
    InferenceProfile(
        id="balanced",
        name="Balanced",
        description="General-purpose defaults. Good for most tasks.",
        temperature=0.7,
    ),
    InferenceProfile(
        id="creative",
        name="Creative",
        description="Higher temperature for brainstorming, writing, and exploration.",
        temperature=1.0,
        top_p=0.95,
    ),
    InferenceProfile(
        id="precise",
        name="Precise",
        description="Low temperature for factual, deterministic output.",
        temperature=0.2,
        top_k=40,
    ),
    InferenceProfile(
        id="code",
        name="Code",
        description="Tuned for code generation and editing. Thinking enabled.",
        temperature=0.3,
        think=True,
    ),
]


# ── Persistence ────────────────────────────────────────────────────────────

def _profiles_dir() -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / "profiles"


def _load_user_profiles() -> list[InferenceProfile]:
    """Load user-created profiles from disk."""
    d = _profiles_dir()
    if not d.is_dir():
        return []
    profiles: list[InferenceProfile] = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            profiles.append(InferenceProfile.model_validate(data))
        except Exception:
            logger.warning("Failed to load profile %s", f.name)
    return profiles


def _save_profile(profile: InferenceProfile) -> None:
    """Persist a user-created profile to disk."""
    d = _profiles_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{profile.id}.json"
    path.write_text(json.dumps(profile.model_dump(), indent=2))


# ── Registry API ───────────────────────────────────────────────────────────

def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    for p in _BUILTINS:
        _PROFILE_REGISTRY[p.id] = p
    for p in _load_user_profiles():
        _PROFILE_REGISTRY[p.id] = p
    _loaded = True


def register_profile(profile: InferenceProfile) -> None:
    """Register a profile and persist it to disk."""
    _ensure_loaded()
    _PROFILE_REGISTRY[profile.id] = profile
    # Only persist non-builtin profiles
    builtin_ids = {p.id for p in _BUILTINS}
    if profile.id not in builtin_ids:
        _save_profile(profile)


def get_profile(profile_id: str) -> InferenceProfile | None:
    """Look up a profile by ID."""
    _ensure_loaded()
    return _PROFILE_REGISTRY.get(profile_id)


def list_profiles() -> list[InferenceProfile]:
    """Return all registered profiles."""
    _ensure_loaded()
    return list(_PROFILE_REGISTRY.values())


def apply_profile(
    profile: InferenceProfile,
    options: "LLMOptions",
) -> "LLMOptions":
    """Merge a profile into LLMOptions.

    Profile values act as defaults — any explicitly set option takes
    precedence. Returns a new LLMOptions instance.
    """
    from agents.types import LLMOptions

    profile_vals = {
        "temperature": profile.temperature,
        "top_k": profile.top_k,
        "top_p": profile.top_p,
        "repeat_penalty": profile.repeat_penalty,
        "num_predict": profile.num_predict,
        "reasoning_effort": profile.reasoning_effort,
        "think": profile.think,
        "max_iterations": profile.max_iterations,
    }

    merged: dict = options.model_dump()
    for key, profile_val in profile_vals.items():
        if profile_val is not None and merged.get(key) is None:
            merged[key] = profile_val

    return LLMOptions.model_validate(merged)


__all__ = [
    "apply_profile",
    "get_profile",
    "list_profiles",
    "register_profile",
]
