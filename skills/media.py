"""Media skill — GPU inference for image and audio generation."""

from textwrap import dedent

from sdk.skills import Skill
from tools.generation import generate_media
from tools.virtual_computer import run_bash_cmd

_SKILL = Skill(
    name="media",
    description="Image and audio generation via GPU inference",
    prompt=dedent("""\
        GPU inference for image and audio generation.

        IMAGES — use generate_media(description). It handles GPU, model loading,
        VRAM, and delivers to the UI automatically. Do NOT call output_file after
        generate_media. NEVER load Flux models directly — always use generate_media.
        Available models: "quality" (default), "photorealistic", "fast".


        SOUND EFFECTS — for game sounds, UI sounds, bleeps, explosions, etc.,
        write a Python script with run_bash_cmd that generates WAV files
        programmatically (numpy + wave module, or ffmpeg). Do NOT use TTS/voice
        tools for sound effects.

        Call send_file(path) and play_audio(path) for all audio output.
        Use describe_image(path, prompt) to analyze images from the container.
        Do NOT run "pip install torch" — it overwrites the CUDA build.
        Save outputs to /home/computron/. Files there are served by the web
        server, so HTML can reference them as src="/home/computron/…".
    """),
    tools=[
        generate_media,
        run_bash_cmd,
    ],
)
