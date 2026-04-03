# ACE-Step Music Generation Integration Plan

## Overview

This plan outlines the integration of [ACE-Step/ACE-Step-v1-3.5B](https://huggingface.co/ACE-Step/ACE-Step-v1-3.5B) - a state-of-the-art open-source music generation model - into COMPUTRON_9000 as a tool capability.

**Note: This replaces the previous Foundation-1 integration plan.**

## Model Analysis

### ACE-Step Specifications
- **Model ID**: ACE-Step/ACE-Step-v1-3.5B
- **Model Type**: Diffusion-based text-to-music
- **Parameters**: 3.5B
- **Output**: Stereo audio, 44.1kHz
- **Max Duration**: 4 minutes (240 seconds)
- **License**: Apache 2.0 (commercial use allowed)
- **Speed**: ~20 seconds for 4-minute music on A100 (15× faster than LLM baselines)

### Key Features
- Full song generation (not just samples/loops)
- Natural language prompts (no structured format required)
- Duration control (30s to 4 minutes)
- High-quality instrumental music generation
- Commercial-friendly Apache 2.0 license

### Prompt Style
ACE-Step uses natural language descriptions:
```
"Upbeat electronic dance music with driving bassline and energetic synth leads"
"Melancholic piano ballad with strings and ambient pads"
"Fast-paced rock instrumental with electric guitars and drums"
"Lo-fi hip hop beats with jazz samples and vinyl crackle"
```

## Comparison: Foundation-1 vs ACE-Step

| Feature | Foundation-1 | ACE-Step |
|---------|--------------|----------|
| Model Size | ~2.4GB | 3.5B parameters |
| Max Duration | ~19 seconds | 4 minutes |
| Prompt Style | Structured (bars, BPM, key, scale) | Natural language |
| License | Stability AI Community | Apache 2.0 ✅ |
| Output Type | Samples/loops | Full songs |
| VRAM Required | ~8GB | ~12GB |

## Implementation

### Files Modified

1. **container/inference_server.py**
   - Updated `_AUDIO_MODEL` to use ACE-Step configuration
   - Changed model ID from "RoyalCities/Foundation-1" to "ACE-Step/ACE-Step-v1-3.5B"
   - Updated `_load_audio_model()` to use DiffusionPipeline with trust_remote_code
   - Simplified `_generate_audio()` to use duration parameter instead of bars/BPM/key/scale
   - Updated default steps from 75 to 27

2. **tools/generation/generate_music.py**
   - Simplified parameters: removed bars, bpm, key, scale
   - Added duration parameter (seconds, max 240)
   - Updated docstrings for ACE-Step

3. **tests/container/test_inference_server_audio.py**
   - Updated to test ACE-Step model configuration
   - Changed from bars/BPM calculation to duration parameter
   - Updated expected model name to "ace-step"

4. **tests/tools/generation/test_generate_music.py**
   - Updated to test ACE-Step parameters (duration instead of bars/bpm/key/scale)
   - Removed tests for removed parameters

5. **agents/computron/agent.py, agents/media/agent.py, agents/sub_agent/agent.py**
   - Updated prompts to reflect natural language style (no structured format required)

### Parameters

ACE-Step uses these simplified parameters:

```python
async def generate_music(
    prompt: str,                    # Natural language description
    negative_prompt: str = "",     # Things to avoid
    duration: float = 30.0,        # Seconds (max 240)
    steps: int = 27,              # Inference steps
    cfg_scale: float = 7.0,       # Guidance scale
    seed: int = -1,               # Random seed
) -> dict[str, str]
```

## Agent Prompt Guidelines

### Natural Language Prompts
ACE-Step works best with descriptive natural language:

**Good prompts:**
- "Energetic electronic dance music with driving bass and synth leads"
- "Melancholic ambient piano with strings and reverb"
- "Upbeat funk groove with brass section and slap bass"
- "Cinematic orchestral score with epic drums and choir"

**Tips:**
- Describe genre, mood, and instrumentation
- Mention specific instruments or sounds
- Include atmosphere descriptors (reverb, space, etc.)
- No need for technical parameters (BPM, key, etc.)

## VRAM Requirements

ACE-Step requires approximately 12GB VRAM:
- Fits on RTX 3060 (12GB) with model CPU offloading
- Recommended: RTX 3090/3090 Ti (24GB) for faster generation
- Uses ACEStepPipeline's built-in `cpu_offload=True` for memory efficiency

## Branch Strategy

```bash
# Branch already exists from Foundation-1 work
git checkout feature/foundation-1-music-generation

# Changes committed:
# - Updated inference_server.py for ACE-Step
# - Updated generate_music.py for ACE-Step parameters
# - Updated test files
# - Updated agent prompts

git push -u origin feature/foundation-1-music-generation
```

## Success Criteria

- [x] Inference server loads ACE-Step model
- [x] Audio generation works via `/generate` endpoint
- [x] Streaming generation works via `/generate-stream` endpoint
- [x] Host tool `generate_music` successfully generates audio files
- [x] Generated audio plays correctly in the UI
- [x] Agents can use the tool to generate music
- [x] All tests pass
- [x] Documentation updated

## References

- [ACE-Step Model Card](https://huggingface.co/ACE-Step/ACE-Step-v1-3.5B)
- [ACE-Step Paper](https://arxiv.org/abs/2506.07520)
- [ACE-Step GitHub](https://github.com/ace-step/ace-step)
