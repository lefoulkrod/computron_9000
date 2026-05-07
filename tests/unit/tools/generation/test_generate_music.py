"""Unit tests for the generate_music tool.

Tests cover:
- Async function signature and existence
- Parameter validation (duration)
- Event publishing (GenerationPreviewPayload, FileOutputPayload)
- Mocked subprocess calls
- Error handling
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.generation.generate_music import generate_music


@pytest.fixture
def mock_subprocess():
    """Create a mock subprocess."""
    proc = AsyncMock()
    proc.returncode = 0
    proc.stdout = AsyncMock()
    proc.stderr = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    return proc


@pytest.mark.unit
async def test_generate_music_function_exists_and_is_async():
    """Test that generate_music is an async function with correct signature."""
    import inspect

    assert inspect.iscoroutinefunction(generate_music)

    sig = inspect.signature(generate_music)
    params = list(sig.parameters.keys())

    expected_params = ["prompt", "lyrics", "duration", "quality"]
    for param in expected_params:
        assert param in params, "Missing parameter: %s" % param

    hidden_params = ["bars", "bpm", "key", "scale", "negative_prompt",
                     "steps", "cfg_scale", "seed"]
    for param in hidden_params:
        assert param not in params, "Should not be exposed: %s" % param


@pytest.mark.unit
async def test_generate_music_default_parameters():
    """Test generate_music with default parameters."""
    with (
        patch("tools.generation.generate_music.publish_event"),
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[
            json.dumps({"status": "loading", "message": "Loading model..."}).encode(),
            json.dumps({"status": "generating", "step": 1, "total_steps": 60}).encode(),
            json.dumps({"status": "complete", "path": "/home/computron/generated_audio/generated_12345.wav"}).encode(),
            b"",
        ])
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_exec.return_value = mock_proc

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "is_file", return_value=True):
            result = await generate_music("upbeat electronic music")

        assert result["status"] == "ok"
        assert result["media_type"] == "audio"
        assert "path" in result


@pytest.mark.unit
async def test_generate_music_custom_parameters():
    """Test generate_music with custom ACE-Step parameters."""
    with (
        patch("tools.generation.generate_music.publish_event"),
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[
            json.dumps({"status": "complete", "path": "/home/computron/generated_audio/generated_12345.wav"}).encode(),
            b"",
        ])
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_exec.return_value = mock_proc

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "is_file", return_value=True):
            result = await generate_music(
                prompt="jazz piano",
                lyrics="[verse]\nSmooth keys in the night",
                duration=30,
                quality="best",
            )

        assert result["status"] == "ok"

        call_args = mock_exec.call_args
        assert call_args is not None
        # python3 -c <script>
        script_arg = call_args[0][2]
        assert "jazz piano" in script_arg
        assert "duration" in script_arg
        assert "'steps': 16" in script_arg
        assert "'thinking': True" in script_arg


@pytest.mark.unit
@pytest.mark.parametrize("duration", [10, 30, 60, 120])
async def test_generate_music_valid_duration(duration):
    """Test generate_music accepts valid duration values (in seconds)."""
    with (
        patch("tools.generation.generate_music.publish_event"),
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[
            json.dumps({"status": "complete", "path": "/home/computron/generated_audio/generated_12345.wav"}).encode(),
            b"",
        ])
        mock_proc.stderr = AsyncMock()
        mock_exec.return_value = mock_proc

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "is_file", return_value=True):
            result = await generate_music("test prompt", duration=duration)
            assert result["status"] == "ok"


@pytest.mark.unit
async def test_generate_music_publishes_generation_preview_events():
    """Test that generate_music publishes GenerationPreviewPayload events."""
    with (
        patch("tools.generation.generate_music.publish_event") as mock_publish,
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[
            json.dumps({"status": "loading", "message": "Loading model..."}).encode(),
            json.dumps({"status": "generating", "step": 1, "total_steps": 60, "message": "Step 1/60"}).encode(),
            json.dumps({"status": "complete", "path": "/home/computron/generated_audio/generated_12345.wav"}).encode(),
            b"",
        ])
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_exec.return_value = mock_proc

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "is_file", return_value=True):
            await generate_music("test prompt")

        calls = mock_publish.call_args_list
        assert len(calls) > 0

        preview_calls = [
            call for call in calls
            if len(call.args) > 0
            and hasattr(call.args[0], "payload")
            and call.args[0].payload.type == "generation_preview"
        ]
        assert len(preview_calls) > 0


@pytest.mark.unit
async def test_generate_music_handles_failed_status():
    """Test that generate_music handles failed generation status."""
    with (
        patch("tools.generation.generate_music.publish_event"),
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[
            json.dumps({"status": "failed", "message": "Model failed to load"}).encode(),
            b"",
        ])
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_exec.return_value = mock_proc

        result = await generate_music("test prompt")

        assert result["status"] == "error"
        assert "Model failed to load" in result["message"]


@pytest.mark.unit
async def test_generate_music_handles_timeout():
    """Test that generate_music handles timeout errors."""
    with (
        patch("tools.generation.generate_music.publish_event"),
        patch("asyncio.create_subprocess_exec") as mock_exec,
        patch("asyncio.wait_for", side_effect=TimeoutError()),
    ):
        mock_proc = AsyncMock()
        mock_exec.return_value = mock_proc

        result = await generate_music("test prompt")

        assert result["status"] == "error"
        assert "timed out" in result["message"].lower()


@pytest.mark.unit
async def test_generate_music_subprocess_command_structure():
    """Test that generate_music constructs correct subprocess command."""
    with (
        patch("tools.generation.generate_music.publish_event"),
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[
            json.dumps({"status": "complete", "path": "/home/computron/generated_audio/generated_12345.wav"}).encode(),
            b"",
        ])
        mock_proc.stderr = AsyncMock()
        mock_exec.return_value = mock_proc

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "is_file", return_value=True):
            await generate_music("ambient synth", duration=60, quality="fast")

        call_args = mock_exec.call_args
        assert call_args is not None
        args = call_args[0]

        assert args[0] == "python3"
        assert args[1] == "-c"

        script = args[2]
        assert "inference_client" in script
        assert "generate_stream" in script
        assert "'steps': 4" in script
        assert "'thinking': False" in script
