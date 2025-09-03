"""Tests for implementation plan management under virtual computer workspace."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from tools.virtual_computer.workspace import (
    get_current_workspace_folder,
    get_current_workspace_plan_json,
    save_plan_json,
    set_workspace_folder,
    reset_workspace_folder,
)


class DummyConfig:
    class Settings:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir
            self.container_working_dir = "/home/computron"

    def __init__(self, home_dir: str) -> None:
        self.settings = self.Settings(home_dir)
        self.virtual_computer = self.VirtualComputer(home_dir)


@pytest.mark.unit
def test_plan_externalization_and_access_via_tool(tmp_path: Path) -> None:
    # Arrange
    with mock.patch("config.load_config", return_value=DummyConfig(str(tmp_path))):
        try:
            set_workspace_folder("ws_abc")
            assert get_current_workspace_folder() == "ws_abc"

            # Act: save a plan (ensures external directory exists)
            plan_data = {"steps": [{"id": "1", "title": "Do X"}]}
            plan_path = Path(save_plan_json(plan_data))
            assert plan_path.exists()
            assert plan_path.name == "plan.json"

            # Tool retrieval returns JSON string
            text = get_current_workspace_plan_json()
            loaded = json.loads(text)
            assert loaded == plan_data
        finally:
            reset_workspace_folder()
