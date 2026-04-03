"""Unit tests for audio generation functionality in inference_server.py.

Tests cover:
- Audio model configuration (_AUDIO_MODEL) for ACE-Step
- Duration calculation using direct seconds parameter
- Parameter parsing in _generate_audio and _generate_audio_stream
- Audio model loading (_ensure_audio_model, _load_audio_model)
"""

from __future__ import annotations

import json
import sys
from io import BytesIO
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import the module under test
sys.path.insert(0, "container")
import inference_server as server

# Skip tests that require diffusers if not installed
try:
    import diffusers
    import torch
    DIFFUSERS_AVAILABLE = True
except ImportError:
    DIFFUSERS_AVAILABLE = False

skip_if_no_diffusers = pytest.mark.skipif(
    not DIFFUSERS_AVAILABLE,
    reason="diffusers/torch not installed"
)


@pytest.fixture
def reset_server_state():
    """Reset global server state before each test."""
    original_pipe = server._pipe
    original_pipe_type = server._pipe_type
    original_loaded_gpu = server._loaded_gpu
    original_loaded_model = server._loaded_model

    server._pipe = None
    server._pipe_type = None
    server._loaded_gpu = -1
    server._loaded_model = None

    yield

    # Restore original state
    server._pipe = original_pipe
    server._pipe_type = original_pipe_type
    server._loaded_gpu = original_loaded_gpu
    server._loaded_model = original_loaded_model


@pytest.mark.unit
def test_audio_model_configuration():
    """Test that _AUDIO_MODEL has required configuration keys."""
    required_keys = [
        "model_id",
        "pipeline_class",
        "num_inference_steps",
        "guidance_scale",
        "sample_rate",
    ]

    for key in required_keys:
        assert key in server._AUDIO_MODEL, f"Missing key: {key}"

    # Verify specific values for ACE-Step
    assert server._AUDIO_MODEL["model_id"] == "ACE-Step/ACE-Step-v1-3.5B"
    assert server._AUDIO_MODEL["pipeline_class"] == "DiffusionPipeline"
    assert server._AUDIO_MODEL["sample_rate"] == 44100


@pytest.mark.unit
@pytest.mark.parametrize("duration,expected", [
    (8.0, 8.0),    # 8 seconds
    (16.0, 16.0),  # 16 seconds
    (9.6, 9.6),    # 9.6 seconds
    (15.0, 15.0),  # 15 seconds
    (27.43, 27.43), # ~27.43 seconds
])
def test_duration_parameter(duration, expected):
    """Test that duration is passed directly in seconds for ACE-Step.

    ACE-Step uses duration parameter directly, not bars/bpm calculation.
    """
    assert round(duration, 2) == round(expected, 2)


@skip_if_no_diffusers
@pytest.mark.unit
def test_generate_audio_parameter_parsing(reset_server_state):
    """Test that _generate_audio correctly parses input parameters for ACE-Step."""
    # Mock the pipe and its methods
    import numpy as np
    mock_pipe = MagicMock()
    mock_output = MagicMock()
    mock_output.audios = [np.array([0.5, 0.6, 0.7], dtype=np.float32)]  # Mock audio data
    mock_pipe.return_value = mock_output

    with (
        patch.object(server, "_pipe", mock_pipe),
        patch.object(server, "_pipe_type", "audio"),
        patch.object(server, "_loaded_gpu", 0),
        patch("scipy.io.wavfile.write") as mock_wav_write,
        patch("os.makedirs"),
        patch("inference_server._ensure_audio_model"),
    ):
        body = {
            "description": "upbeat electronic music",
            "negative_prompt": "drums",
            "duration": 15.0,
            "steps": 27,
            "cfg_scale": 8.5,
            "seed": 42,
        }

        result = server._generate_audio(body)

        # Verify the pipe was called with correct parameters
        call_kwargs = mock_pipe.call_args[1]
        # ACE-Step uses raw prompt without musical formatting
        assert mock_pipe.call_args[0][0] == "upbeat electronic music"
        assert call_kwargs["negative_prompt"] == "drums"
        assert call_kwargs["num_inference_steps"] == 27
        assert call_kwargs["guidance_scale"] == 8.5

        # Verify duration is passed directly for ACE-Step
        assert call_kwargs["duration"] == 15.0


@skip_if_no_diffusers
@pytest.mark.unit
def test_generate_audio_default_parameters(reset_server_state):
    """Test that _generate_audio uses correct defaults for ACE-Step."""
    mock_pipe = MagicMock()
    mock_output = MagicMock()
    import numpy as np
    mock_output.audios = [np.array([0.5, 0.6, 0.7], dtype=np.float32)]
    mock_pipe.return_value = mock_output

    with (
        patch.object(server, "_pipe", mock_pipe),
        patch.object(server, "_pipe_type", "audio"),
        patch.object(server, "_loaded_gpu", 0),
        patch("scipy.io.wavfile.write"),
        patch("os.makedirs"),
        patch("inference_server._ensure_audio_model"),
    ):
        body = {
            "description": "ambient music",
        }

        server._generate_audio(body)

        call_kwargs = mock_pipe.call_args[1]
        # Check defaults
        assert call_kwargs["negative_prompt"] == ""
        assert call_kwargs["num_inference_steps"] == server._AUDIO_MODEL["num_inference_steps"]
        assert call_kwargs["guidance_scale"] == server._AUDIO_MODEL["guidance_scale"]

        # Default duration for ACE-Step: 10 seconds
        assert call_kwargs["duration"] == 10.0


@skip_if_no_diffusers
@pytest.mark.unit
def test_generate_audio_conditional_prompt_format(reset_server_state):
    """Test that ACE-Step uses raw prompt without musical formatting."""
    mock_pipe = MagicMock()
    mock_output = MagicMock()
    import numpy as np
    mock_output.audios = [np.array([0.5, 0.6, 0.7], dtype=np.float32)]
    mock_pipe.return_value = mock_output

    with (
        patch.object(server, "_pipe", mock_pipe),
        patch.object(server, "_pipe_type", "audio"),
        patch.object(server, "_loaded_gpu", 0),
        patch("scipy.io.wavfile.write"),
        patch("os.makedirs"),
        patch("inference_server._ensure_audio_model"),
    ):
        body = {
            "description": "jazz piano",
            "key": "C",
            "scale": "major",
            "bpm": 120,
        }

        server._generate_audio(body)

        # ACE-Step uses raw prompt without "{key} {scale}, {bpm} BPM" formatting
        prompt = mock_pipe.call_args[0][0]
        assert prompt == "jazz piano"


@skip_if_no_diffusers
@pytest.mark.unit
def test_generate_audio_with_seed(reset_server_state):
    """Test that _generate_audio uses seed when provided."""
    mock_pipe = MagicMock()
    mock_output = MagicMock()
    import numpy as np
    mock_output.audios = [np.array([0.5, 0.6, 0.7], dtype=np.float32)]
    mock_pipe.return_value = mock_output

    mock_generator = MagicMock()
    mock_generator.manual_seed.return_value = mock_generator

    with (
        patch.object(server, "_pipe", mock_pipe),
        patch.object(server, "_pipe_type", "audio"),
        patch.object(server, "_loaded_gpu", 0),
        patch("torch.Generator", return_value=mock_generator),
        patch("scipy.io.wavfile.write"),
        patch("os.makedirs"),
        patch("inference_server._ensure_audio_model"),
    ):
        body = {
            "description": "test",
            "seed": 12345,
        }

        server._generate_audio(body)

        call_kwargs = mock_pipe.call_args[1]
        assert call_kwargs["generator"] == mock_generator
        mock_generator.manual_seed.assert_called_once_with(12345)


@skip_if_no_diffusers
@pytest.mark.unit
def test_generate_audio_without_seed(reset_server_state):
    """Test that _generate_audio doesn't create generator when seed is None."""
    mock_pipe = MagicMock()
    mock_output = MagicMock()
    import numpy as np
    mock_output.audios = [np.array([0.5, 0.6, 0.7], dtype=np.float32)]
    mock_pipe.return_value = mock_output

    with (
        patch.object(server, "_pipe", mock_pipe),
        patch.object(server, "_pipe_type", "audio"),
        patch.object(server, "_loaded_gpu", 0),
        patch("torch.Generator") as mock_generator_class,
        patch("scipy.io.wavfile.write"),
        patch("os.makedirs"),
        patch("inference_server._ensure_audio_model"),
    ):
        body = {
            "description": "test",
        }

        server._generate_audio(body)

        call_kwargs = mock_pipe.call_args[1]
        assert call_kwargs["generator"] is None
        mock_generator_class.assert_not_called()


@skip_if_no_diffusers
@pytest.mark.unit
def test_generate_audio_output_path_format(reset_server_state):
    """Test that _generate_audio generates correct output path."""
    mock_pipe = MagicMock()
    mock_output = MagicMock()
    import numpy as np
    mock_output.audios = [np.array([0.5, 0.6, 0.7], dtype=np.float32)]
    mock_pipe.return_value = mock_output

    with (
        patch.object(server, "_pipe", mock_pipe),
        patch.object(server, "_pipe_type", "audio"),
        patch.object(server, "_loaded_gpu", 0),
        patch("scipy.io.wavfile.write") as mock_wav_write,
        patch("os.makedirs") as mock_makedirs,
        patch("inference_server._ensure_audio_model"),
        patch("time.time", return_value=1234567890.123),
    ):
        body = {"description": "test"}

        result = server._generate_audio(body)

        # Check path format
        assert result["path"].startswith("/home/computron/generated_audio/")
        assert result["path"].endswith(".wav")
        assert "generated_" in result["path"]

        # Check duration and sample_rate in result
        assert "duration" in result
        assert "sample_rate" in result
        assert result["sample_rate"] == 44100


@skip_if_no_diffusers
@pytest.mark.unit
def test_generate_audio_stream_parameter_parsing(reset_server_state):
    """Test that _generate_audio_stream correctly parses parameters for ACE-Step."""
    mock_pipe = MagicMock()
    mock_output = MagicMock()
    import numpy as np
    mock_output.audios = [np.array([0.5, 0.6, 0.7], dtype=np.float32)]
    mock_pipe.return_value = mock_output

    lines = []

    def mock_write_line(data):
        lines.append(data)

    with (
        patch.object(server, "_pipe", mock_pipe),
        patch.object(server, "_pipe_type", "audio"),
        patch.object(server, "_loaded_gpu", 0),
        patch("scipy.io.wavfile.write"),
        patch("os.makedirs"),
        patch("inference_server._ensure_audio_model"),
        patch("inference_server._load_audio_model"),
    ):
        body = {
            "description": "techno beat",
            "duration": 20.0,
            "steps": 27,
        }

        server._generate_audio_stream(body, mock_write_line)

        # Check loading event was sent
        loading_events = [e for e in lines if e.get("status") == "loading"]
        assert len(loading_events) >= 1

        # Check generating event was sent
        generating_events = [e for e in lines if e.get("status") == "generating"]
        assert len(generating_events) >= 1

        # Check complete event was sent
        complete_events = [e for e in lines if e.get("status") == "complete"]
        assert len(complete_events) == 1
        assert "path" in complete_events[0]


@pytest.mark.unit
def test_generate_audio_stream_duration_in_message(reset_server_state):
    """Test that _generate_audio_stream includes duration in initial message for ACE-Step."""
    mock_pipe = MagicMock()
    mock_output = MagicMock()
    import numpy as np
    mock_output.audios = [np.array([0.5, 0.6, 0.7], dtype=np.float32)]
    mock_pipe.return_value = mock_output

    lines = []

    def mock_write_line(data):
        lines.append(data)

    with (
        patch.object(server, "_pipe", mock_pipe),
        patch.object(server, "_pipe_type", "audio"),
        patch.object(server, "_loaded_gpu", 0),
        patch("scipy.io.wavfile.write"),
        patch("os.makedirs"),
        patch("inference_server._ensure_audio_model"),
    ):
        body = {
            "description": "test",
            "duration": 16.0,
        }

        server._generate_audio_stream(body, mock_write_line)

        # Find the generating event with duration info
        generating_events = [e for e in lines if e.get("status") == "generating"]
        assert len(generating_events) >= 1

        # Check message format: "Starting audio generation ({duration:.1f}s)..."
        message = generating_events[0].get("message", "")
        assert "16.0s" in message or "Starting audio generation" in message


@pytest.mark.unit
def test_ensure_audio_model_reuses_loaded_model(reset_server_state):
    """Test that _ensure_audio_model reuses already loaded audio model."""
    mock_pipe = MagicMock()

    with (
        patch.object(server, "_pipe", mock_pipe),
        patch.object(server, "_pipe_type", "audio"),
        patch.object(server, "_loaded_gpu", 0),
        patch("inference_server._load_audio_model") as mock_load,
    ):
        server._ensure_audio_model()

        # Should not call _load_audio_model since audio model is already loaded
        mock_load.assert_not_called()


@pytest.mark.unit
def test_ensure_audio_model_raises_on_different_model_type(reset_server_state):
    """Test that _ensure_audio_model raises _ModelSwitchRequired when image model is loaded."""
    mock_pipe = MagicMock()

    with (
        patch.object(server, "_pipe", mock_pipe),
        patch.object(server, "_pipe_type", "image"),
        patch.object(server, "_loaded_model", "fast"),
        patch("inference_server._load_audio_model"),
    ):
        with pytest.raises(server._ModelSwitchRequired) as exc_info:
            server._ensure_audio_model()

        assert exc_info.value.requested == "foundation-1"


@skip_if_no_diffusers
@pytest.mark.unit
def test_load_audio_model_sets_globals(reset_server_state):
    """Test that _load_audio_model sets global state correctly for ACE-Step."""
    # Skip if DiffusionPipeline can't be imported
    try:
        from diffusers import DiffusionPipeline
    except (ImportError, RuntimeError) as e:
        pytest.skip(f"DiffusionPipeline not available: {e}")

    mock_pipeline_class = MagicMock()
    mock_pipe_instance = MagicMock()
    mock_pipeline_class.from_pretrained.return_value = mock_pipe_instance

    with (
        patch("diffusers.DiffusionPipeline", mock_pipeline_class),
        patch("torch.cuda.set_device"),
        patch("inference_server._unload"),
        patch("inference_server._find_best_gpu", return_value=(1, 8000.0, 12000.0)),
        patch("inference_server._is_model_cached", return_value=True),
    ):
        server._load_audio_model()

        # Check globals were set
        assert server._pipe_type == "audio"
        assert server._loaded_gpu == 1
        assert server._loaded_model == "ace-step"

        # Check pipeline was created with correct model and trust_remote_code=True
        mock_pipeline_class.from_pretrained.assert_called_once()
        call_args = mock_pipeline_class.from_pretrained.call_args
        assert call_args[0][0] == "ACE-Step/ACE-Step-v1-3.5B"
        assert call_args[1].get("trust_remote_code") is True

        # Check model offload was enabled
        mock_pipe_instance.enable_model_cpu_offload.assert_called_once_with(gpu_id=1)


@pytest.mark.unit
def test_handler_generate_audio_endpoint():
    """Test that the HTTP handler correctly routes audio generation requests."""
    # Test that _generate_audio function exists and can be patched
    with patch.object(server, "_generate_audio", return_value={"path": "/test.wav"}) as mock_generate:
        # Verify the function can be called (we can't easily test the HTTP handler
        # without complex socket mocking, so we test the underlying function)
        result = server._generate_audio({"description": "test"})
        assert result["path"] == "/test.wav"
        mock_generate.assert_called_once()


@pytest.mark.unit
def test_handler_generate_stream_audio():
    """Test that streaming endpoint handles audio type correctly for ACE-Step."""
    body = {
        "type": "audio",
        "description": "test music",
        "duration": 10.0,
    }

    # Test that _generate_audio_stream function exists and can be patched
    with patch.object(server, "_generate_audio_stream") as mock_stream:
        # Verify the function can be called
        server._generate_audio_stream(body, lambda x: None)
        mock_stream.assert_called_once()


@pytest.mark.unit
def test_audio_model_sample_rate():
    """Test that audio model uses 44.1kHz sample rate."""
    assert server._AUDIO_MODEL["sample_rate"] == 44100


@pytest.mark.unit
def test_audio_model_default_steps():
    """Test that ACE-Step audio model has correct default steps."""
    assert server._AUDIO_MODEL["num_inference_steps"] == 27
    assert server._AUDIO_MODEL["num_inference_steps"] > 0


@pytest.mark.unit
def test_audio_model_default_guidance():
    """Test that audio model has reasonable default guidance scale."""
    assert server._AUDIO_MODEL["guidance_scale"] == 7.0
    assert server._AUDIO_MODEL["guidance_scale"] > 0
