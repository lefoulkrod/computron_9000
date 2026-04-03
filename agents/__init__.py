"""The agents package contains AI agent definitions."""

__all__ = ["AVAILABLE_AGENTS", "resolve_agent"]


def __getattr__(name: str) -> object:
    """Lazy imports to avoid circular dependency with sdk."""
    if name in ("AVAILABLE_AGENTS", "resolve_agent"):
        from agents._registry import AVAILABLE_AGENTS, resolve_agent
        return {"AVAILABLE_AGENTS": AVAILABLE_AGENTS, "resolve_agent": resolve_agent}[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
