"""Tests for implementation plan management."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from tools.virtual_computer.implementation_artifacts import (
    get_plan_json,
    save_plan_json,
)


class DummyConfig:
    class Settings:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    def __init__(self, home_dir: str) -> None:
        self.settings = self.Settings(home_dir)


@pytest.mark.unit
def test_plan_save_and_retrieve(tmp_path: Path) -> None:
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        plan_data = {"steps": [{"id": "1", "title": "Do X"}]}
        plan_path = Path(save_plan_json(plan_data, name="test_plan"))
        assert plan_path.exists()
        assert plan_path.name == "plan.json"

        text = get_plan_json(name="test_plan")
        loaded = json.loads(text)
        assert loaded == plan_data
