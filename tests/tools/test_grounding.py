"""Tests for the shared grounding client (tools/_grounding.py)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tools._grounding import GroundingResponse, _parse_response, run_grounding


# ── _parse_response tests ─────────────────────────────────────────────


_VALID_SERVER_OUTPUT = json.dumps({
    "thought": "I see a Save button",
    "action": "click(start_box='(640,360)')",
    "action_type": "click",
    "coordinates": [{"model": [640, 360], "screen": [640, 360]}],
    "x": 640,
    "y": 360,
    "image_size": [1280, 720],
    "raw": "Thought: I see a Save button\nAction: click(...)",
})


@pytest.mark.unit
def test_parse_response_success() -> None:
    """Valid JSON output should parse into a GroundingResponse."""
    response = _parse_response(_VALID_SERVER_OUTPUT)
    assert isinstance(response, GroundingResponse)
    assert response.x == 640
    assert response.y == 360
    assert response.thought == "I see a Save button"
    assert response.action_type == "click"
    assert response.raw["image_size"] == [1280, 720]


@pytest.mark.unit
def test_parse_response_skips_log_lines() -> None:
    """Log messages before the JSON line should be skipped."""
    raw = "Loading model...\nWarmup complete.\n" + _VALID_SERVER_OUTPUT
    response = _parse_response(raw)
    assert response.x == 640


@pytest.mark.unit
def test_parse_response_no_json() -> None:
    """Output with no JSON should raise RuntimeError."""
    with pytest.raises(RuntimeError, match="no JSON"):
        _parse_response("some random output\nno json here")


@pytest.mark.unit
def test_parse_response_no_coordinates() -> None:
    """JSON without coordinates should succeed with x=None, y=None."""
    data = json.dumps({"thought": "hmm", "action_type": "wait"})
    response = _parse_response(data)
    assert response.x is None
    assert response.y is None
    assert response.action_type == "wait"
    assert response.thought == "hmm"


@pytest.mark.unit
def test_parse_response_type_action() -> None:
    """Type action should parse with no coordinates."""
    data = json.dumps({
        "thought": "Need to type text",
        "action_type": "type",
        "type_content": "hello world",
    })
    response = _parse_response(data)
    assert response.x is None
    assert response.y is None
    assert response.action_type == "type"
    assert response.raw["type_content"] == "hello world"


@pytest.mark.unit
def test_parse_response_hotkey_action() -> None:
    """Hotkey action should parse with no coordinates."""
    data = json.dumps({
        "thought": "Press ctrl+c",
        "action_type": "hotkey",
        "hotkey": "ctrl+c",
    })
    response = _parse_response(data)
    assert response.x is None
    assert response.y is None
    assert response.action_type == "hotkey"
    assert response.raw["hotkey"] == "ctrl+c"


@pytest.mark.unit
def test_parse_response_finished_action() -> None:
    """Finished action should parse with no coordinates."""
    data = json.dumps({
        "thought": "Task is done",
        "action_type": "finished",
        "finished_content": "The login was successful",
    })
    response = _parse_response(data)
    assert response.x is None
    assert response.y is None
    assert response.action_type == "finished"
    assert response.raw["finished_content"] == "The login was successful"


@pytest.mark.unit
def test_parse_response_uses_coordinates_fallback() -> None:
    """When x/y are missing, fall back to coordinates[0].screen."""
    data = json.dumps({
        "thought": "",
        "action_type": "click",
        "coordinates": [{"model": [100, 200], "screen": [150, 250]}],
    })
    response = _parse_response(data)
    assert response.x == 150
    assert response.y == 250


# ── run_grounding tests ───────────────────────────────────────────────


class _FakeInferenceConfig:
    home_dir = "/tmp/test_grounding_home"
    container_name = "test_inference"
    container_working_dir = "/home/testuser"


class _FakeConfig:
    inference_container = _FakeInferenceConfig()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_grounding_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """run_grounding should write screenshot to .vision/, exec podman, and return parsed result."""
    fake_cfg = _FakeConfig()
    fake_cfg.inference_container.home_dir = str(tmp_path)

    monkeypatch.setattr("tools._grounding.load_config", lambda: fake_cfg)

    fake_result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=_VALID_SERVER_OUTPUT.encode(),
        stderr=b"",
    )
    monkeypatch.setattr("tools._grounding.subprocess.run", lambda *a, **kw: fake_result)

    response = await run_grounding(b"fake-png-bytes", "Click the Save button")

    assert isinstance(response, GroundingResponse)
    assert response.x == 640
    assert response.y == 360

    # Verify screenshot was written to .vision/ subdirectory
    # Default agent_id is None → "default", so filename is grounding_default.png
    screenshot_path = tmp_path / ".vision" / "grounding_default.png"
    assert screenshot_path.exists()
    assert screenshot_path.read_bytes() == b"fake-png-bytes"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_grounding_custom_filename(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Custom screenshot_filename should be used for the file on disk."""
    fake_cfg = _FakeConfig()
    fake_cfg.inference_container.home_dir = str(tmp_path)

    monkeypatch.setattr("tools._grounding.load_config", lambda: fake_cfg)

    fake_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=_VALID_SERVER_OUTPUT.encode(), stderr=b"",
    )
    monkeypatch.setattr("tools._grounding.subprocess.run", lambda *a, **kw: fake_result)

    await run_grounding(b"png", "task", screenshot_filename="browser_screenshot.png")

    assert (tmp_path / ".vision" / "browser_screenshot.png").exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_grounding_uses_ground_from_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """run_grounding should use ground_from_path (no base64) in the exec script."""
    fake_cfg = _FakeConfig()
    fake_cfg.inference_container.home_dir = str(tmp_path)

    monkeypatch.setattr("tools._grounding.load_config", lambda: fake_cfg)

    captured_args: list = []

    def capture_run(*args, **kwargs):
        captured_args.append(args)
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_VALID_SERVER_OUTPUT.encode(), stderr=b"",
        )

    monkeypatch.setattr("tools._grounding.subprocess.run", capture_run)

    await run_grounding(b"png", "task")

    # The script should reference ground_from_path, not ground + base64
    script_cmd = captured_args[0][0]  # first positional arg to subprocess.run
    script_text = script_cmd[-1]  # last element is the -c script
    assert "ground_from_path" in script_text
    assert "base64" not in script_text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_grounding_subprocess_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Non-zero exit code from podman exec should raise RuntimeError."""
    fake_cfg = _FakeConfig()
    fake_cfg.inference_container.home_dir = str(tmp_path)

    monkeypatch.setattr("tools._grounding.load_config", lambda: fake_cfg)

    fake_result = subprocess.CompletedProcess(
        args=[], returncode=1, stdout=b"", stderr=b"container not found",
    )
    monkeypatch.setattr("tools._grounding.subprocess.run", lambda *a, **kw: fake_result)

    with pytest.raises(RuntimeError, match="container not found"):
        await run_grounding(b"png", "task")
