"""Music generation skill — song and instrumental creation."""

from textwrap import dedent

from sdk.skills import Skill
from tools.generation import generate_music
from tools.virtual_computer import play_audio, send_file

_SKILL = Skill(
    name="music_generation",
    description="Generate full songs and instrumental music from text prompts",
    prompt=dedent("""\
        Music generation using ACE-Step 1.5.

        generate_music(prompt, lyrics, duration, quality, style) — creates
        full songs and instrumental music.
        - prompt: be specific — genre, vocal type, emotion, instruments, tempo,
          key, production style. E.g. "pop-rock, powerful female vocal, energetic,
          driving drums, 128 bpm, E major"
        - lyrics: structure tags like [verse], [chorus], [bridge], [intro],
          [outro]. Add style hints: [verse - whispered], [chorus - powerful].
          Use "[Instrumental]" for no vocals.
        - duration: seconds (max 600). Sweet spot: 90-120s for vocals,
          60-90s for instrumental.
        - quality: "fast" (instant drafts), "quality" (default), "best"
          (highest fidelity)
        - style: genre preset that auto-tunes parameters — "pop", "rock",
          "hiphop", "electronic", "jazz", "classical", "ambient", "metal",
          "lofi". Leave empty to use defaults.

        Call send_file(path) for every generated file and play_audio(path) to
        play audio in the browser. Never just mention the path.

        SOUND EFFECTS — for game sounds, UI sounds, bleeps, explosions, etc.,
        use run_bash_cmd to generate WAV files programmatically (numpy + wave
        module, or ffmpeg). Do NOT use generate_music for sound effects.
    """),
    tools=[
        generate_music,
        play_audio,
        send_file,
    ],
)
