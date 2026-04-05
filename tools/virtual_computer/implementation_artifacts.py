"""Implementation artifact management helpers.

Stores implementation plans under ``settings.home_dir/implementation_plans``.
Agents access plans via tool functions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)


def _get_implementation_plans_root() -> Path:
    """Return the absolute root directory for implementation plans."""
    cfg = config.load_config()
    return Path(cfg.settings.home_dir).expanduser().resolve() / "implementation_plans"


def save_plan_json(plan: dict[str, Any] | list[Any] | str, name: str = "default") -> str:
    """Save an implementation plan as ``plan.json``.

    Args:
        plan: The plan content as a dict/list (JSON-serialized) or a JSON string.
        name: Plan name used as the subdirectory. Defaults to "default".

    Returns:
        str: The absolute path to the saved plan.json file.
    """
    plan_dir = _get_implementation_plans_root() / name
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "plan.json"
    try:
        if isinstance(plan, str):
            json.loads(plan)
            plan_path.write_text(plan, encoding="utf-8")
        else:
            plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.exception("Failed to save plan.json for %s", name)
        raise
    return str(plan_path)


def get_plan_json(name: str = "default") -> str:
    """Return the plan.json content for a given plan name.

    Returns:
        str: The JSON string content of ``plan.json``.
    """
    plan_dir = _get_implementation_plans_root() / name
    plan_path = plan_dir / "plan.json"
    try:
        content = plan_path.read_text(encoding="utf-8")
        json.loads(content)
    except Exception:
        logger.exception("Failed to retrieve plan.json for %s", name)
        raise
    else:
        return content


__all__ = [
    "get_plan_json",
    "save_plan_json",
]
