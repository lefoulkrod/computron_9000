"""Tool for listing available agent profiles."""

from agents._agent_profiles import list_agent_profiles as _list_profiles


def list_agent_profiles() -> str:
    """List all available agent profiles that can be used with spawn_agent.

    Returns:
        A formatted list of profile IDs, names, and descriptions.
    """
    profiles = _list_profiles()
    if not profiles:
        return "No agent profiles available."
    lines = [
        f"  - {p.id}: {p.name} — {p.description} (model={p.model}, skills={p.skills})"
        for p in profiles
    ]
    return "Available agent profiles:\n" + "\n".join(lines)
