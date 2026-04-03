"""Unit tests for the generate_music tool.

Tests cover:
- Async function signature and existence
- Parameter validation (duration)
- Event publishing (GenerationPreviewPayload, FileOutputPayload)
- Mocked podman exec calls
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
def mock_config():
    """Mock configuration for inference container."""
    config = MagicMock()
    config.inference_container.container_name = "test-inference-container"
    config.inference_container.container_user = "computron"
    config.inference_container.container_working_dir = "/home/computron"
    config.inference_container.home_dir = "/tmp/test_computron"
    return config


@pytest.fixture
def mock_subprocess():
    """Create a mock subprocess for podman exec calls."""
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

    # Check signature includes expected parameters
    sig = inspect.signature(generate_music)
    params = list(sig.parameters.keys())

    expected_params = [
        "prompt",
        "lyrics",
        "duration",
        "quality",
    ]
    for param in expected_params:
        assert param in params, f"Missing parameter: {param}"

    # Ensure raw pipeline params are not exposed (presets handle these)
    hidden_params = ["bars", "bpm", "key", "scale", "negative_prompt",
                     "steps", "cfg_scale", "seed"]
    for param in hidden_params:
        assert param not in params, f"Should not be exposed: {param}"


@pytest.mark.unit
async def test_generate_music_default_parameters(mock_config):
    """Test generate_music with default parameters."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        # Setup mock subprocess
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[
            json.dumps({"status": "loading", "message": "Loading model..."}).encode(),
            json.dumps({"status": "generating", "step": 1, "total_steps": 60}).encode(),
            json.dumps({"status": "complete", "path": "/home/computron/generated_audio/generated_12345.wav"}).encode(),
            b"",  # EOF
        ])
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_exec.return_value = mock_proc

        # Mock Path.exists for the generated file
        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "is_file", return_value=True):
            result = await generate_music("upbeat electronic music")

        assert result["status"] == "ok"
        assert result["media_type"] == "audio"
        assert "path" in result


@pytest.mark.unit
async def test_generate_music_custom_parameters(mock_config):
    """Test generate_music with custom ACE-Step parameters."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
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

        # Verify the subprocess was called with correct parameters
        call_args = mock_exec.call_args
        assert call_args is not None
        script_arg = call_args[0][7]  # 7th positional argument is the script
        assert "jazz piano" in script_arg
        assert "duration" in script_arg
        # "best" vocal preset uses euler scheduler, 80 steps, higher guidance_interval
        assert "euler" in script_arg
        assert '"steps": 80' in script_arg
        assert "guidance_interval" in script_arg


@pytest.mark.unit
@pytest.mark.parametrize("duration", [10, 30, 60, 120])
async def test_generate_music_valid_duration(mock_config, duration):
    """Test generate_music accepts valid duration values (in seconds)."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
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
async def test_generate_music_publishes_generation_preview_events(mock_config):
    """Test that generate_music publishes GenerationPreviewPayload events."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[
            json.dumps({"status": "loading", "message": "Loading model..."}).encode(),
            json.dumps({"status": "generating", "step": 1, "total_steps": 60, "message": "Step 1/60"}).encode(),
            json.dumps({"status": "generating", "step": 60, "total_steps": 60, "message": "Finalizing..."}).encode(),
            json.dumps({"status": "complete", "path": "/home/computron/generated_audio/generated_12345.wav"}).encode(),
            b"",
        ])
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_exec.return_value = mock_proc

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "is_file", return_value=True):
            await generate_music("test prompt")

        # Check that publish_event was called with GenerationPreviewPayload
        calls = mock_publish.call_args_list
        assert len(calls) > 0

        # Verify at least one call has GenerationPreviewPayload
        # publish_event is called with AgentEvent as positional arg
        preview_calls = [
            call for call in calls
            if len(call.args) > 0
            and hasattr(call.args[0], "payload")
            and call.args[0].payload.type == "generation_preview"
        ]
        assert len(preview_calls) > 0


@pytest.mark.unit
async def test_generate_music_publishes_file_output_event(mock_config):
    """Test that generate_music publishes FileOutputPayload on completion."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
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
            await generate_music("test prompt")

        # Check that FileOutputPayload was published
        calls = mock_publish.call_args_list
        file_output_calls = [
            call for call in calls
            if len(call.args) > 0
            and hasattr(call.args[0], "payload")
            and call.args[0].payload.type == "file_output"
        ]
        assert len(file_output_calls) == 1

        payload = file_output_calls[0].args[0].payload
        assert payload.filename == "generated_12345.wav"
        assert payload.content_type in ("audio/wav", "audio/x-wav")


@pytest.mark.unit
async def test_generate_music_handles_failed_status(mock_config):
    """Test that generate_music handles failed generation status."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
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
async def test_generate_music_handles_nonzero_returncode(mock_config):
    """Test that generate_music handles subprocess failure."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[b""])
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"Container not found")
        mock_exec.return_value = mock_proc

        result = await generate_music("test prompt")

        assert result["status"] == "error"
        assert "Container not found" in result["message"]


@pytest.mark.unit
async def test_generate_music_handles_timeout(mock_config):
    """Test that generate_music handles timeout errors."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
        patch("asyncio.create_subprocess_exec") as mock_exec,
        patch("asyncio.wait_for", side_effect=TimeoutError()),
    ):
        mock_proc = AsyncMock()
        mock_exec.return_value = mock_proc

        result = await generate_music("test prompt")

        assert result["status"] == "error"
        assert "timed out" in result["message"].lower()


@pytest.mark.unit
async def test_generate_music_handles_general_exception(mock_config):
    """Test that generate_music handles unexpected exceptions."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
        patch("asyncio.create_subprocess_exec", side_effect=Exception("Unexpected error")),
    ):
        result = await generate_music("test prompt")

        assert result["status"] == "error"
        assert "Unexpected error" in result["message"]


@pytest.mark.unit
async def test_generate_music_no_output_path(mock_config):
    """Test that generate_music handles missing output path."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[b""])  # No complete event
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_exec.return_value = mock_proc

        result = await generate_music("test prompt")

        assert result["status"] == "error"
        assert "No output path received" in result["message"]


@pytest.mark.unit
async def test_generate_music_file_not_found_on_host(mock_config):
    """Test that generate_music handles file not found on host gracefully."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
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

        # File doesn't exist on host
        with patch.object(Path, "exists", return_value=False):
            result = await generate_music("test prompt")

        # Should still return ok but with warning
        assert result["status"] == "ok"


@pytest.mark.unit
async def test_generate_music_parses_json_lines_correctly(mock_config):
    """Test that generate_music correctly parses JSONL output from subprocess."""
    events = [
        {"status": "loading", "message": "Loading ACE-Step model..."},
        {"status": "generating", "step": 10, "total_steps": 60, "message": "Step 10/60"},
        {"status": "generating", "step": 20, "total_steps": 60, "message": "Step 20/60"},
        {"status": "complete", "path": "/home/computron/generated_audio/generated_12345.wav", "duration": 30.0},
    ]

    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(
            side_effect=[json.dumps(e).encode() for e in events] + [b""]
        )
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_exec.return_value = mock_proc

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "is_file", return_value=True):
            result = await generate_music("test prompt")

        assert result["status"] == "ok"
        assert result["path"] == "/home/computron/generated_audio/generated_12345.wav"


@pytest.mark.unit
async def test_generate_music_skips_non_json_lines(mock_config):
    """Test that generate_music skips non-JSON lines gracefully."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
        patch("tools.generation.generate_music.publish_event") as mock_publish,
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[
            b"Some log output that is not JSON",
            json.dumps({"status": "complete", "path": "/home/computron/generated_audio/generated_12345.wav"}).encode(),
            b"",
        ])
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_exec.return_value = mock_proc

        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "is_file", return_value=True):
            result = await generate_music("test prompt")

        assert result["status"] == "ok"


@pytest.mark.unit
async def test_generate_music_podman_exec_command_structure(mock_config):
    """Test that generate_music constructs correct podman exec command for ACE-Step."""
    with (
        patch("tools.generation.generate_music.load_config", return_value=mock_config),
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
            await generate_music(
                "ambient synth",
                duration=60,
                quality="fast",
            )

        # Verify podman exec was called with correct arguments
        call_args = mock_exec.call_args
        assert call_args is not None
        args = call_args[0]

        assert args[0] == "podman"
        assert args[1] == "exec"
        assert args[2] == "-u"
        assert args[3] == "computron"
        assert args[4] == "test-inference-container"
        assert args[5] == "python3"
        assert args[6] == "-c"

        # Check the script contains expected ACE-Step parameters
        script = args[7]
        assert "inference_client" in script
        assert "generate_stream" in script
        assert "ambient synth" in script or "ambient" in script.lower()
        assert "duration" in script
        # "fast" instrumental preset uses pingpong scheduler, 25 steps
        assert "pingpong" in script
        assert '"steps": 25' in script
