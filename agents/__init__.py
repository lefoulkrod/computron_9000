"""The agents package contains AI agent definitions."""

__all__ = [
    "AVAILABLE_AGENTS",
    "apply_profile",
    "get_profile",
    "list_profiles",
    "register_profile",
    "resolve_agent",
]


def __getattr__(name: str) -> object:
    """Lazy imports to avoid circular dependency with sdk."""
    if name in ("AVAILABLE_AGENTS", "resolve_agent"):
        from agents._registry import AVAILABLE_AGENTS, resolve_agent
        return {"AVAILABLE_AGENTS": AVAILABLE_AGENTS, "resolve_agent": resolve_agent}[name]
    if name in ("apply_profile", "get_profile", "list_profiles", "register_profile"):
        from agents._profiles import apply_profile, get_profile, list_profiles, register_profile
        return {
            "apply_profile": apply_profile,
            "get_profile": get_profile,
            "list_profiles": list_profiles,
            "register_profile": register_profile,
        }[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
