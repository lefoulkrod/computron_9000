"""Execution policy for bash commands in the virtual computer.

Pure validation logic with no project imports — safe to import without
triggering circular dependencies.
"""

from __future__ import annotations

import re

# Deny patterns indicating long-running servers/watchers
_DENY_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Popular package managers invoking dev/start
    re.compile(r"(?<!\S)(npm|pnpm|yarn|bun)\s+(run\s+)?dev\b", re.IGNORECASE),
    re.compile(r"(?<!\S)(npm|pnpm|yarn|bun)\s+(run\s+)?start\b", re.IGNORECASE),
    # Framework CLIs invoking dev/start/serve
    re.compile(r"(?<!\S)(vite|astro|nuxt|next|svelte(?:-kit)?|turbo)\s+dev\b", re.IGNORECASE),
    re.compile(r"(?<!\S)(next|nuxt|astro)\s+start\b", re.IGNORECASE),
    re.compile(r"(?<!\S)(vue-cli-service|ng)\s+serve\b", re.IGNORECASE),
    # 'watch' the Linux command (long-running) — only at command position
    # (start of string, after pipe, semicolon, or &&), not inside heredoc content.
    re.compile(r"(?:^|[|;&])\s*watch\b", re.IGNORECASE),
    # Watch flags: block plain flag or explicit enabling; allow explicit false/0
    re.compile(r"--watch(All)?(?:\s|$)", re.IGNORECASE),
    re.compile(r"--watch(All)?\s*=\s*(?!false\b|0\b)\S+", re.IGNORECASE),
    re.compile(r"tail\s+-f"),
    re.compile(r"sleep\s+inf(inity)?", re.IGNORECASE),
    re.compile(r"python3?\s+-m\s+http\.server"),
    re.compile(r"playwright\b.*\bheaded\b", re.IGNORECASE),
)


def is_allowed_command(cmd: str) -> bool:
    """Check if a command is permitted by execution policy.

    Conservative rule: block only when a deny pattern matches; otherwise allow.

    Args:
        cmd: The command string to evaluate.

    Returns:
        True if allowed; False if a deny pattern matches or empty input.
    """
    stripped = cmd.strip()
    if not stripped:
        return False
    return all(not pat.search(stripped) for pat in _DENY_PATTERNS)
