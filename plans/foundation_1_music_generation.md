# Foundation-1 Music Generation Integration Plan

## Overview

This plan outlines the integration of [RoyalCities/Foundation-1](https://huggingface.co/RoyalCities/Foundation-1) - a structured text-to-sample music generation model - into COMPUTRON_9000 as a tool capability.

## Model Analysis

### Foundation-1 Specifications
- **Base Model**: stabilityai/stable-audio-open-1.0
- **Model Type**: diffusion_cond (conditional diffusion)
- **Output**: Stereo audio, 44.1kHz, ~19s for 8-bar @ 100 BPM
- **Parameters**: 2.43 GB (Foundation_1.safetensors)
- **License**: Stability AI Community License

### Key Features
- Structured text-to-sample generation for music production
- Musical structure awareness: BPM, bars, key, scale
- Instrument hierarchy: Synth, Keys, Bass, Bowed Strings, Mallet, Wind, Guitar, Brass, Vocal, Plucked Strings
- Timbral control: spectral shape, tone, width, density, texture, brightness, warmth, grit
- FX layer: reverb, delay, distortion, phaser, bitcrushing
- Notation-aware: chord progressions, melodies, arps, phrase direction

### Prompt Structure
```
[Instrument Family], [Sub-Family], [Timbre Tags], [FX Tags], [Notation], [Bars], [BPM], [Key]

Example:
"Kalimba, Mallet, Medium Reverb, Overdriven, Wide, Metallic, Thick, Sparkly, 
Upper Mids, Bright, Airy, Alternating Chord Progression, Atmosphere, Spacey, 
Fast Speed, 8 Bars, 120 BPM, B minor"
```

## Current Architecture Analysis

### Inference System
The existing inference system consists of:

1. **inference_server.py** (container-side)
   - Persistent HTTP server on port 18901
   - Keeps models loaded in VRAM between requests
   - Endpoints: `/generate`, `/generate-stream`, `/health`, `/shutdown`
   - Currently supports: `image` (Flux), `video` (Wan2.1)
   - Model registry pattern with `_MODELS` dict
   - Streaming with JSONL progress updates

2. **inference_client.py** (container-side)
   - Thin client that auto-starts server
   - `generate(type, description, **params)` - blocking
   - `generate_stream(type, description, **params)` - streaming

3. **generate_media.py** (host-side)
   - Host tool that calls container client via podman exec
   - Publishes `GenerationPreviewPayload` events
   - Returns file output for chat

### Decision: Extend vs New

**RECOMMENDATION: Extend existing inference system**

Rationale:
1. Foundation-1 uses the same Stable Audio architecture that can leverage existing patterns
2. The model registry pattern in inference_server.py is designed for extensibility
3. The streaming infrastructure (JSONL progress, file output) is reusable
4. A separate audio inference server would waste VRAM and complicate GPU management

## Implementation Plan

### Phase 1: Inference Server Updates

#### 1.1 Add Audio Model to Registry
Add Foundation-1 to `_MODELS` registry in `inference_server.py`:

```python
_MODELS = {
    # ... existing image models ...
    "foundation-1": {
        "model_id": "RoyalCities/Foundation-1",
        "base_model": "stabilityai/stable-audio-open-1.0",
        "pipeline_class": "StableAudioPipeline",  # or custom wrapper
        "num_inference_steps": 75,
        "guidance_scale": 7.0,
        "sample_rate": 44100,
        "audio_channels": 2,
    },
}
```

#### 1.2 Add Audio Model Loader
Create `_load_audio_model()` function similar to `_load_video_model()`:
- Load Stable Audio pipeline
- Handle model weights (Foundation_1.safetensors)
- Configure for GPU with CPU offloading
- Set `_pipe_type = "audio"`

#### 1.3 Add Audio Generation Functions
Create `_generate_audio()` and `_generate_audio_stream()`:
- Parse prompt for structured parameters (bars, BPM, key, scale)
- Calculate duration: `duration = (bars * 4 beats/bar) / (BPM / 60) seconds`
- Generate audio using pipeline
- Save as WAV or MP3
- Stream progress (Stable Audio doesn't have step callbacks, but we can simulate)

#### 1.4 Update HTTP Handlers
Modify `_handle_generate()` and `_handle_generate_stream()`:
- Accept `gen_type == "audio"`
- Route to audio generation functions

### Phase 2: Inference Client Updates

#### 2.1 Update Client Functions
Modify `generate()` and `generate_stream()` in `inference_client.py`:
- Already support generic `gen_type` parameter
- Add audio-specific params: `bars`, `bpm`, `key`, `scale`, `negative_prompt`
- No breaking changes needed

### Phase 3: Host Tool Implementation

#### 3.1 Extend or Create Tool
**Option A: Extend `generate_media.py`**
- Add `media_type="audio"` support
- Add music-specific parameters
- Pros: Single tool for all media generation
- Cons: Parameter bloat, different UI needs

**Option B: Create `generate_music.py`**
- Dedicated tool for music generation
- Music-specific parameters: `prompt`, `negative_prompt`, `bars`, `bpm`, `key`, `scale`, `steps`, `cfg_scale`, `seed`
- Pros: Clean API, music-focused
- Cons: Another tool to maintain

**RECOMMENDATION: Option B - Create `generate_music.py`**

Rationale:
- Music generation has unique parameters (bars, BPM, key, scale)
- Different output handling (audio playback vs image display)
- Clearer agent instructions

#### 3.2 Tool Interface
```python
async def generate_music(
    prompt: str,
    negative_prompt: str = "",
    bars: int = 8,
    bpm: int = 128,
    key: str = "C",
    scale: str = "minor",
    steps: int = 75,
    cfg_scale: float = 7.0,
    seed: int = -1,
) -> dict[str, str]:
    """Generate music using Foundation-1 model.
    
    Args:
        prompt: Text prompt describing the music (instrument, timbre, FX, notation)
        negative_prompt: Things to avoid in the generation
        bars: Number of bars (4 or 8 recommended)
        bpm: Tempo in beats per minute (100-150)
        key: Musical key (A, A#, B, C, C#, D, D#, E, F, F#, G, G#)
        scale: major or minor
        steps: Inference steps (higher = better quality, slower)
        cfg_scale: CFG scale (guidance strength)
        seed: Random seed (-1 for random)
    
    Returns:
        Dict with status, path, and media_type
    """
```

### Phase 4: Agent Integration

#### 4.1 Update Agent Tool Lists
Add `generate_music` to:
- `agents/computron/agent.py` - main agent
- `agents/media/agent.py` - media specialist agent
- `agents/sub_agent/agent.py` - sub-agent

#### 4.2 Update Agent Prompts
Add instructions for music generation:
- When to use generate_music vs generate_media
- Prompt structure guidelines
- Parameter recommendations

### Phase 5: Testing

#### 5.1 Unit Tests
- Test inference server audio loading
- Test audio generation with various parameters
- Test streaming progress
- Test error handling

#### 5.2 Integration Tests
- Test full pipeline: tool → client → server → generation
- Test file output and playback
- Test concurrent requests

#### 5.3 Manual Testing
- Generate various music styles
- Test different BPM/bar combinations
- Verify audio quality and loop points

## File Changes Summary

### Modified Files
1. `container/inference_server.py`
   - Add Foundation-1 to model registry
   - Add `_load_audio_model()` function
   - Add `_generate_audio()` function
   - Add `_generate_audio_stream()` function
   - Update HTTP handlers for audio type

2. `container/inference_client.py`
   - Update docstrings for audio support
   - (No code changes needed - already generic)

3. `tools/generation/__init__.py`
   - Export `generate_music`

4. `agents/computron/agent.py`
   - Import `generate_music`
   - Add to TOOLS list
   - Update system prompt

5. `agents/media/agent.py`
   - Import `generate_music`
   - Add to TOOLS list
   - Update system prompt

6. `agents/sub_agent/agent.py`
   - Import `generate_music`
   - Add to TOOLS list

### New Files
1. `tools/generation/generate_music.py`
   - Host tool for music generation
   - Streaming support with progress events
   - File output handling

2. `tests/test_generate_music.py`
   - Unit tests for music generation tool

## Dependencies

### Container Dependencies
The inference container already has:
- torch, torchaudio (2.6.0)
- diffusers
- transformers

Additional dependencies needed:
- `stable-audio-tools` or similar for Stable Audio pipeline
- `audiocraft` (optional, for additional audio utilities)

### Installation
```bash
# In container/Dockerfile or requirements
pip install stable-audio-tools
```

## VRAM Requirements

Foundation-1 (based on Stable Audio Open):
- Base model: ~2-4 GB
- With CPU offloading: Works on 8GB GPUs
- Recommended: 12GB+ for faster generation

The existing `_find_best_gpu()` logic should handle this automatically.

## Prompt Engineering Guidelines for Agents

### Prompt Structure Template
```
[Instrument Family], [Sub-Family], [Timbre Tags], [FX Tags], [Notation/Structure], [Bars], [BPM], [Key]
```

### Required Elements
- **Bars**: 4 or 8 (defines loop length)
- **BPM**: 100-150 (tempo)
- **Key**: A-G with optional # (sharp)
- **Scale**: major or minor

### Instrument Families
Synth, Keys, Bass, Bowed Strings, Mallet, Wind, Guitar, Brass, Vocal, Plucked Strings

### Example Prompts for Agent
1. "Synth Lead, Supersaw, Bright, Wide, Punchy, Melody, Epic, 8 Bars, 128 BPM, C minor"
2. "Bass, FM Bass, Gritty, Acid, 303, Overdriven, Bassline, 4 Bars, 140 BPM, E minor"
3. "Kalimba, Mallet, Metallic, Sparkly, Bright, Chord Progression, 8 Bars, 120 BPM, B minor"

## Branch Strategy

```bash
# Create feature branch
git checkout -b feature/foundation-1-music-generation

# Implementation commits
# 1. Update inference server
# 2. Update inference client
# 3. Add generate_music tool
# 4. Update agents
# 5. Add tests

# Push and create PR
git push -u origin feature/foundation-1-music-generation
```

## Success Criteria

- [ ] Inference server can load Foundation-1 model
- [ ] Audio generation works via `/generate` endpoint
- [ ] Streaming generation works via `/generate-stream` endpoint
- [ ] Host tool `generate_music` successfully generates audio files
- [ ] Generated audio plays correctly in the UI
- [ ] Agents can use the tool to generate music
- [ ] All tests pass
- [ ] Documentation updated

## Future Enhancements

1. **Audio-to-Audio**: Foundation-1 supports audio conditioning for style transfer
2. **Prompt Builder**: Helper to construct structured prompts from natural language
3. **Batch Generation**: Generate multiple variations with different seeds
4. **Integration with DAW**: Export to project files or MIDI
5. **Additional Models**: Support other Stable Audio fine-tunes

## References

- [Foundation-1 Model Card](https://huggingface.co/RoyalCities/Foundation-1)
- [Stable Audio Open](https://huggingface.co/stabilityai/stable-audio-open-1.0)
- [Foundation-1 Space](https://huggingface.co/spaces/multimodalart/Foundation-1)
- [Master Tag Reference](https://huggingface.co/RoyalCities/Foundation-1/blob/main/Master_Tag_Reference.md)
