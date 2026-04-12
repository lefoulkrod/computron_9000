"""Tool for listing available agent profiles."""


def list_agent_profiles() -> str:
    """List all available agent profiles that can be used with spawn_agent.

    Returns:
        A formatted list of profile IDs, names, and descriptions.
    """
    from agents._agent_profiles import list_agent_profiles as _list

    profiles = _list()
    if not profiles:
        return "No agent profiles available."
    lines = [
        f"  - {p.id}: {p.name} — {p.description} (model={p.model}, skills={p.skills})"
        for p in profiles
    ]
    return "Available agent profiles:\n" + "\n".join(lines)
