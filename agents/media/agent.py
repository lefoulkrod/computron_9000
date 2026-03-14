"""GPU inference agent — specialized for all GPU-accelerated workloads.

Handles image and audio generation using the persistent inference server,
HuggingFace model management, prompt engineering, VRAM management, and custom
diffusion/ML model workflows.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from agents.browser import browser_agent_tool
from sdk import make_run_agent_as_tool_function
from tools.custom_tools import lookup_custom_tools, run_custom_tool
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.generation import generate_media
from tools.virtual_computer import describe_image, output_file, play_audio, run_bash_cmd

logger = logging.getLogger(__name__)

NAME = "INFERENCE_AGENT"
DESCRIPTION = (
    "GPU inference specialist — generates images and audio, "
    "manages HuggingFace models, and handles all GPU-accelerated workloads."
)
SYSTEM_PROMPT = dedent(
    """
    You are INFERENCE_AGENT, a GPU inference specialist inside COMPUTRON_9000.

    IMAGES — ALWAYS use generate_media(description). It handles GPU, model loading,
    VRAM, and delivers to the UI automatically. Do NOT call output_file after generate_media.
    NEVER load Flux models directly — always use generate_media.
    Available models: "quality" (default, best results), "photorealistic" (realistic photos),
    "fast" (quick drafts). Pick based on the request.

    VOICE / TTS — use run_custom_tool to invoke voice tools (generate_voice_audio, etc.).
    Use lookup_custom_tools(action="search", query="audio") to discover available tools.
    Voice tools are for spoken words / narration only.

    SOUND EFFECTS — for game sounds, UI sounds, bleeps, explosions, ambient loops, etc.,
    write a Python script with run_bash_cmd that generates WAV files programmatically
    (e.g. numpy + wave module, or ffmpeg). Do NOT use TTS/voice tools for sound effects.

    Call output_file(path) and play_audio(path) for all audio output.

    Use describe_image(path, prompt) to analyze images from the container.
    Use run_browser_agent_as_tool for web browsing or accepting gated model licenses.
    Do NOT run "pip install torch" — it overwrites the CUDA build.
    Save outputs to /home/computron/. Files there are served by the web server,
    so HTML can reference them as src="/home/computron/…" — never base64-encode.
    Provide a brief summary with file paths when done.
    """
)
TOOLS = [
    generate_media,
    run_bash_cmd,
    run_custom_tool,
    lookup_custom_tools,
    output_file,
    play_audio,
    describe_image,
    browser_agent_tool,
    save_to_scratchpad,
    recall_from_scratchpad,
]

inference_agent_tool = make_run_agent_as_tool_function(
    name=NAME,
    description=DESCRIPTION,
    instruction=SYSTEM_PROMPT,
    tools=TOOLS,
)

# Keep backward-compatible alias
media_agent_tool = inference_agent_tool

__all__ = [
    "DESCRIPTION",
    "NAME",
    "SYSTEM_PROMPT",
    "TOOLS",
    "inference_agent_tool",
    "media_agent_tool",
]
