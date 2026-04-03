"""Persistent inference server for image/video/audio generation.

Keeps ML models loaded in VRAM between requests so custom tools don't
pay the ~30s model-loading cost on every call.  Auto-shuts down after
10 minutes of inactivity to free VRAM for other workloads (e.g. Ollama).

Usage (inside container):
    python3 /opt/inference/inference_server.py &

Protocol:
    POST /generate         — JSON body, blocks until done, returns {"path": ...}
    POST /generate-stream  — JSON body, chunked JSONL with progress + previews
    GET  /health           — returns {"status": "ok", "model": ...}
    POST /shutdown         — graceful shutdown
"""

import base64
import io
import json
import logging
import os
import signal
import sys
import threading
import time
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Suppress noisy library output
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["DIFFUSERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# Ensure torch and nvidia-smi use the same GPU index ordering
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
# Use expandable memory segments to avoid CUDA fragmentation — without
# this, PyTorch reserves fixed-size blocks that can't be reused for
# differently-sized allocations, wasting GB of VRAM on 12 GB cards.
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
warnings.filterwarnings("ignore")

# Read HF token from file if not already in environment
if not os.environ.get("HF_TOKEN"):
    _token_path = os.path.expanduser("~/.cache/huggingface/token")
    if os.path.isfile(_token_path):
        with open(_token_path) as _f:
            _tok = _f.read().strip()
            if _tok:
                os.environ["HF_TOKEN"] = _tok

PORT = 18901
PID_FILE = "/tmp/inference_server.pid"
IDLE_TIMEOUT = 180  # 3 minutes

logging.basicConfig(
    level=logging.INFO,
    format="[inference] %(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("inference")

# ── Model registry ────────────────────────────────────────────────────
_DEFAULT_MODEL = "fast"

_MODELS = {
    "quality": {
        "model_id": "black-forest-labs/FLUX.1-dev",
        "pipeline_class": "FluxPipeline",
        "loras": [
            {"id": "enhanceaiteam/Flux-Uncensored-V2", "weight_name": "lora.safetensors", "scale": 1.0},
        ],
        "num_inference_steps": 20,
        "guidance_scale": 3.5,
        "taesd_preview": True,
    },
    "photorealistic": {
        "model_id": "black-forest-labs/FLUX.1-dev",
        "pipeline_class": "FluxPipeline",
        "loras": [
            {"id": "enhanceaiteam/Flux-Uncensored-V2", "weight_name": "lora.safetensors", "scale": 1.0},
            {"id": "kudzueye/boreal-flux-dev-v2", "weight_name": "boreal-v2.safetensors", "scale": 0.6},
        ],
        "num_inference_steps": 20,
        "guidance_scale": 3.5,
        "taesd_preview": True,
    },
    "fast": {
        "model_id": "black-forest-labs/FLUX.1-schnell",
        "pipeline_class": "FluxPipeline",
        "loras": [
            {"id": "enhanceaiteam/Flux-Uncensored-V2", "weight_name": "lora.safetensors", "scale": 1.0},
        ],
        "num_inference_steps": 4,
        "guidance_scale": 0.0,
        "taesd_preview": True,
    },
}

# Audio model configuration (ACE-Step for full song generation)
_AUDIO_MODEL = {
    "model_id": "ACE-Step/ACE-Step-v1-3.5B",
    "pipeline_class": "ACEStepPipeline",
    "num_inference_steps": 27,  # Default from ACE-Step docs
    "guidance_scale": 7.0,
    "sample_rate": 44100,
    "max_duration": 240,  # 4 minutes max
}

_SIZE_PRESETS = {
    "square": (1024, 1024),
    "landscape": (768, 1344),
    "portrait": (1344, 768),
    "wide": (768, 1536),
}

# ── GPU selection ─────────────────────────────────────────────────────
_MIN_FREE_VRAM_MB = 8_000  # ~8 GB minimum for Flux with model_cpu_offload + NF4


def _find_best_gpu() -> tuple[int, float, float]:
    """Query GPUs via nvidia-smi and return (index, free_mb, total_mb).

    Prefers more powerful GPUs (higher total VRAM) when they have enough
    free memory to run inference.  Among GPUs that meet the minimum free
    VRAM threshold, the one with the most total VRAM wins — bigger cards
    have more CUDA cores and wider memory buses, so they generate faster.
    Falls back to the GPU with the most free VRAM when no card meets the
    minimum.

    Uses nvidia-smi instead of torch to avoid creating CUDA contexts on
    GPUs we won't use.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.free,memory.total,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            log.warning("nvidia-smi failed: %s", result.stderr.strip())
            return 0, 0.0, 0.0

        gpus: list[tuple[int, float, float, str]] = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 4:
                continue
            idx = int(parts[0])
            free_mb = float(parts[1])
            total_mb = float(parts[2])
            name = parts[3]
            log.info("GPU %d: %s — %.1f GB free / %.1f GB total",
                     idx, name, free_mb / 1024, total_mb / 1024)
            gpus.append((idx, free_mb, total_mb, name))

        if not gpus:
            return 0, 0.0, 0.0

        # Prefer GPUs that meet the minimum free VRAM threshold, then
        # pick the most powerful (highest total VRAM) among those.
        candidates = [(i, f, t, n) for i, f, t, n in gpus
                      if f >= _MIN_FREE_VRAM_MB]
        if candidates:
            # Among viable cards, prefer the most powerful (highest total)
            best = max(candidates, key=lambda g: g[2])
            log.info("Selected GPU %d (%s): %.1f GB free, %.1f GB total (preferred)",
                     best[0], best[3], best[1] / 1024, best[2] / 1024)
        else:
            # No card meets minimum — fall back to most free VRAM
            best = max(gpus, key=lambda g: g[1])
            log.info("No GPU meets %.1f GB minimum; falling back to GPU %d (%s, %.1f GB free)",
                     _MIN_FREE_VRAM_MB / 1024, best[0], best[3], best[1] / 1024)

        return best[0], best[1], best[2]

    except Exception:
        log.warning("GPU detection failed, falling back to cuda:0", exc_info=True)
        return 0, 0.0, 0.0


# ── Global state ──────────────────────────────────────────────────────
_pipe = None
_pipe_type = None  # "image" or "video" or "audio"
_loaded_gpu = -1  # which physical GPU the model is currently on
_loaded_model = None  # name key from _MODELS (e.g. "schnell", "klein-4b")
_taesd = None  # AutoencoderTiny for Flux preview (loaded lazily)
_last_request = time.time()
_lock = threading.Lock()

# Steps at which to emit a first-frame preview for video generation.
_VIDEO_PREVIEW_STEPS = {5, 10, 15, 20}


def _unload():
    """Unload the current model.

    Called during idle shutdown.  NF4 quantized weights (bitsandbytes)
    can't be freed from GPU memory within the same process, so model
    switching is handled by restarting the server process instead.
    """
    global _pipe, _pipe_type, _taesd, _loaded_gpu, _loaded_model
    if _pipe is not None:
        log.info("Unloading %s model (%s) from GPU %d", _pipe_type, _loaded_model, _loaded_gpu)
        del _pipe
        _pipe = None
        _pipe_type = None
        _loaded_gpu = -1
        _loaded_model = None
    if _taesd is not None:
        del _taesd
        _taesd = None


def _ensure_taesd():
    """Load TAESD (AutoencoderTiny) for cheap image previews on CPU."""
    global _taesd
    if _taesd is not None:
        return
    import torch
    from diffusers import AutoencoderTiny

    log.info("Loading TAESD (madebyollin/taef1) for previews...")
    try:
        _taesd = AutoencoderTiny.from_pretrained(
            "madebyollin/taef1", torch_dtype=torch.float32,
        )
    except Exception:
        log.info("Online TAESD load failed, falling back to local cache")
        _taesd = AutoencoderTiny.from_pretrained(
            "madebyollin/taef1", torch_dtype=torch.float32,
            local_files_only=True,
        )
    _taesd = _taesd.to("cpu")
    _taesd.eval()
    log.info("TAESD ready on CPU")


def _unpack_flux_latents(lat, height=None, width=None):
    """Unpack Flux packed latents (batch, seq_len, packed_ch) to (batch, ch, H, W).

    Flux packs latents with 2x2 spatial patches, so packed_channels = latent_channels * 4.
    Returns the unpacked tensor and the detected latent_channels count.
    Returns (None, 0) if the format is unrecognized.

    Args:
        lat: Latent tensor, either already 4D or packed 3D.
        height: Target image height in pixels (needed for non-square images).
        width: Target image width in pixels (needed for non-square images).
    """
    if lat.ndim == 4:
        return lat, lat.shape[1]

    if lat.ndim != 3:
        log.warning("Flux unpack: unexpected ndim=%d", lat.ndim)
        return None, 0

    batch, seq_len, packed_channels = lat.shape
    # Detect latent channel count from packed size (packed = channels * 4)
    if packed_channels == 64:
        latent_channels = 16  # Schnell
    elif packed_channels == 128:
        latent_channels = 32  # Klein
    else:
        log.warning("Flux unpack: unexpected packed_channels=%d", packed_channels)
        return None, 0

    # Determine packed spatial dimensions.  The VAE downsamples 8x and
    # Flux packs 2x2 patches, so each packed axis = pixel_dim // 16.
    if height is not None and width is not None:
        packed_h = height // 16
        packed_w = width // 16
        if packed_h * packed_w != seq_len:
            log.warning("Flux unpack: h/w mismatch %d*%d=%d != seq_len=%d",
                        packed_h, packed_w, packed_h * packed_w, seq_len)
            return None, 0
    else:
        # Fallback: assume square spatial layout
        spatial_side = int(seq_len ** 0.5)
        if spatial_side * spatial_side != seq_len:
            log.warning("Flux unpack: non-square seq_len=%d, pass height/width", seq_len)
            return None, 0
        packed_h = spatial_side
        packed_w = spatial_side

    patch_size = packed_channels // latent_channels  # 4 = 2x2
    spatial_per_patch = int(patch_size ** 0.5)  # 2

    # Unpack: (1, S, packed) → (1, pH, pW, ch, 2, 2) → (1, ch, pH*2, pW*2)
    lat = lat.view(batch, packed_h, packed_w, latent_channels,
                   spatial_per_patch, spatial_per_patch)
    lat = lat.permute(0, 3, 1, 4, 2, 5).contiguous()
    lat = lat.view(batch, latent_channels,
                   packed_h * spatial_per_patch,
                   packed_w * spatial_per_patch)
    return lat, latent_channels


def _decode_preview_taesd(latents, height=None, width=None):
    """Decode Flux latents with TAESD on CPU → base64 JPEG.

    Works for both 16-channel (Schnell) and 32-channel (Klein) latents.
    For 32-channel models, takes the first 16 channels — the TAESD decoder
    still produces recognizable previews showing generation progress.

    Args:
        latents: Packed or unpacked latent tensor from the diffusion callback.
        height: Target image height in pixels (needed for non-square images).
        width: Target image width in pixels (needed for non-square images).
    """
    import torch

    _ensure_taesd()
    try:
        with torch.no_grad():
            lat = latents.detach().float().cpu()
            lat, latent_channels = _unpack_flux_latents(lat, height=height, width=width)
            if lat is None:
                return None
            # TAESD expects 16 channels — for 32-channel models (Klein),
            # take the first 16 channels for an approximate preview.
            if latent_channels == 32:
                lat = lat[:, :16, :, :]
            elif latent_channels != 16:
                log.debug("TAESD: unsupported %d-channel latents", latent_channels)
                return None
            decoded = _taesd.decode(lat).sample
            decoded = decoded.clamp(0, 1)
            decoded = (decoded[0].permute(1, 2, 0).numpy() * 255).astype("uint8")
            from PIL import Image
            img = Image.fromarray(decoded)
            # Scale to fit 512px on the longest side, preserving aspect ratio
            max_dim = 512
            w, h = img.size
            if w >= h:
                img = img.resize((max_dim, int(h * max_dim / w)), Image.LANCZOS)
            else:
                img = img.resize((int(w * max_dim / h), max_dim), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        log.exception("TAESD preview decode failed")
        return None


def _decode_video_first_frame(latents):
    """Decode first frame of video latents through Wan's VAE on CPU → base64 JPEG."""
    import torch

    try:
        with torch.no_grad():
            lat = latents.detach().float().cpu()
            # Wan latents shape: (batch, channels, num_frames, height, width)
            # Extract first frame: (1, C, 1, H, W)
            if lat.ndim == 5 and lat.shape[2] > 1:
                lat = lat[:, :, :1, :, :]

            vae = _pipe.vae
            # Move VAE to CPU for decode
            vae_device = next(vae.parameters()).device
            vae = vae.to("cpu")
            try:
                # Scale latents
                scaling = getattr(vae.config, "scaling_factor", 1.0)
                lat = lat / scaling
                decoded = vae.decode(lat).sample
            finally:
                vae.to(vae_device)

            decoded = decoded.clamp(0, 1)
            # Shape: (1, C, frames, H, W) → take first frame
            if decoded.ndim == 5:
                frame = decoded[0, :, 0, :, :]  # (C, H, W)
            else:
                frame = decoded[0]  # (C, H, W)
            frame = (frame.permute(1, 2, 0).numpy() * 255).astype("uint8")
            from PIL import Image
            img = Image.fromarray(frame)
            # Resize to reasonable preview
            img = img.resize((480, 270), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        log.exception("Video first-frame preview failed")
        return None


def _is_model_cached(model_id: str) -> bool:
    """Check whether a HuggingFace model has already been downloaded."""
    try:
        from huggingface_hub import scan_cache_dir

        cache_info = scan_cache_dir()
        for repo in cache_info.repos:
            if repo.repo_id == model_id:
                for revision in repo.revisions:
                    if revision.nb_files > 0:
                        return True
        return False
    except Exception:
        return False


def _dir_size(path: str) -> int:
    """Return total size in bytes of all files under *path*."""
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def _download_model(model_id: str, on_progress=None):
    """Pre-download model weights with progress updates."""
    from huggingface_hub import model_info as hf_model_info, snapshot_download

    def _emit(msg):
        log.info(msg)
        if on_progress:
            on_progress(msg)

    # Estimate total download size from HF metadata
    total_bytes = 0
    try:
        info = hf_model_info(model_id)
        total_bytes = sum(s.size for s in (info.siblings or []) if s.size)
    except Exception:
        pass

    total_gb = total_bytes / (1024 ** 3) if total_bytes else 0
    size_str = f" (~{total_gb:.1f} GB)" if total_gb > 1 else ""
    _emit(f"Downloading {model_id}{size_str} — this may take several minutes...")

    # Locate the HF cache directory for progress monitoring
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    model_cache_dir = os.path.join(
        cache_dir, "models--" + model_id.replace("/", "--"),
    )

    done = threading.Event()
    error: list[BaseException | None] = [None]

    def _run_download():
        try:
            snapshot_download(model_id)
        except BaseException as exc:
            error[0] = exc
        finally:
            done.set()

    t = threading.Thread(target=_run_download, daemon=True)
    t.start()

    # Emit periodic progress while downloading
    while not done.wait(timeout=5.0):
        try:
            downloaded = _dir_size(model_cache_dir)
            dl_gb = downloaded / (1024 ** 3)
            if total_bytes > 0:
                pct = min(99, int(downloaded / total_bytes * 100))
                _emit(f"Downloading {model_id}... {pct}% ({dl_gb:.1f}/{total_gb:.1f} GB)")
            else:
                _emit(f"Downloading {model_id}... ({dl_gb:.1f} GB downloaded)")
        except Exception:
            pass

    if error[0] is not None:
        raise error[0]  # type: ignore[misc]

    _emit("Download complete.")


class _TqdmProgressForwarder:
    """Intercept tqdm progress bars to forward percentage updates.

    Monkey-patches ``tqdm.auto.tqdm`` so that from_pretrained() weight
    loading, checkpoint shards, and pipeline component loading emit
    progress events through our callback instead of only writing to
    stderr.
    """

    def __init__(self, on_progress, label="Loading"):
        self._on_progress = on_progress
        self._label = label
        self._orig_update = None
        self._orig_init = None
        self._tqdm_mod = None
        self._last_pct = -1  # deduplicate events

    def __enter__(self):
        if not self._on_progress:
            return self
        try:
            import tqdm.auto as tqdm_mod
            self._tqdm_mod = tqdm_mod
            self._orig_init = tqdm_mod.tqdm.__init__
            self._orig_update = tqdm_mod.tqdm.update
            forwarder = self

            orig_init = self._orig_init

            def _patched_init(tqdm_self, *args, **kwargs):
                orig_init(tqdm_self, *args, **kwargs)
                desc = getattr(tqdm_self, "desc", None) or ""
                if desc:
                    forwarder._label = desc.rstrip(": ")

            orig_update = self._orig_update

            def _patched_update(tqdm_self, n=1):
                orig_update(tqdm_self, n)
                total = getattr(tqdm_self, "total", None)
                current_n = getattr(tqdm_self, "n", 0)
                if total and total > 0:
                    pct = int(current_n / total * 100)
                    if pct != forwarder._last_pct:
                        forwarder._last_pct = pct
                        forwarder._on_progress(
                            f"{forwarder._label}... {pct}%"
                        )

            tqdm_mod.tqdm.__init__ = _patched_init
            tqdm_mod.tqdm.update = _patched_update
        except Exception:
            log.debug("Could not patch tqdm for progress forwarding",
                      exc_info=True)
        return self

    def __exit__(self, *exc):
        if self._tqdm_mod is not None and self._orig_init is not None:
            try:
                self._tqdm_mod.tqdm.__init__ = self._orig_init
                self._tqdm_mod.tqdm.update = self._orig_update
            except Exception:
                pass
        self._tqdm_mod = None
        self._orig_init = None
        self._orig_update = None


def _load_image_model(model_name: str, gpu_id: int, free_mb: float,
                      total_mb: float, on_progress=None):
    """Load an image model with quantization and VRAM-adaptive strategy.

    Uses NF4 quantization and chooses between full GPU load (fastest),
    model-level offload, or sequential offload based on available and
    total VRAM.
    """
    global _pipe, _pipe_type, _loaded_gpu, _loaded_model

    def _emit(msg):
        log.info(msg)
        if on_progress:
            on_progress(msg)

    _unload()

    import diffusers
    import torch
    from diffusers import PipelineQuantizationConfig

    model_cfg = _MODELS[model_name]
    model_id = model_cfg["model_id"]
    pipe_cls = getattr(diffusers, model_cfg["pipeline_class"])

    # Pre-download if not cached, with progress updates to the UI
    if not _is_model_cached(model_id):
        _download_model(model_id, on_progress=on_progress)

    # Choose loading strategy based on free VRAM.  NF4 quantization puts
    # the quantized components on GPU during from_pretrained(), so we must
    # account for loading overhead (temporary bf16 buffers during quantization).
    #
    # Thresholds (approximate peak GPU during loading):
    #   full_gpu:       both transformer + text_encoder_2 NF4 on GPU (~10 GB)
    #   model_offload:  transformer NF4 on GPU (~7 GB with loading overhead)
    _MIN_LOAD_VRAM_NF4 = 7_000     # ~7 GB for NF4 transformer loading
    _MIN_LOAD_VRAM_BOTH = 10_000   # ~10 GB for both NF4 components

    if free_mb < _MIN_LOAD_VRAM_NF4:
        raise RuntimeError(
            f"Not enough GPU memory for image generation. "
            f"Best GPU (cuda:{gpu_id}) has only {free_mb / 1024:.1f} GB free, "
            f"need at least {_MIN_LOAD_VRAM_NF4 / 1024:.0f} GB. "
            f"Try again after Ollama unloads some models."
        )

    if free_mb >= _MIN_LOAD_VRAM_BOTH and total_mb >= 16_000:
        strategy = "full_gpu" if free_mb >= 12_000 else "model_offload"
        quant_components = ["transformer", "text_encoder_2"]
    else:
        # Enough for NF4 transformer on GPU; text_encoder_2 stays bf16 on CPU
        strategy = "model_offload"
        quant_components = ["transformer"]

    quant_config = PipelineQuantizationConfig(
        quant_backend="bitsandbytes_4bit",
        quant_kwargs={
            "bnb_4bit_quant_type": "nf4",
            "bnb_4bit_compute_dtype": "bfloat16",
        },
        components_to_quantize=quant_components,
    )

    quant_label = f"NF4 {'+'.join(quant_components)}"
    _emit(f"Loading {model_name} weights ({quant_label}, {strategy})...")

    # Set default CUDA device before from_pretrained() — bitsandbytes
    # quantization loads components directly to the current CUDA device.
    torch.cuda.set_device(gpu_id)

    with _TqdmProgressForwarder(on_progress, label="Loading model"):
        _pipe = pipe_cls.from_pretrained(
            model_id,
            quantization_config=quant_config,
            torch_dtype=torch.bfloat16,
        )

    # Load LoRA adapters if the model config specifies any
    _load_loras(model_cfg, on_progress=on_progress)

    _emit(f"Setting up {strategy} on GPU {gpu_id}...")
    if strategy == "full_gpu":
        _pipe.to(f"cuda:{gpu_id}")
    elif strategy == "model_offload":
        _pipe.enable_model_cpu_offload(gpu_id=gpu_id)
    else:
        _pipe.enable_sequential_cpu_offload(gpu_id=gpu_id)

    # Slice attention when VRAM is tight to reduce peak activation memory
    if free_mb < 10_000:
        _pipe.enable_attention_slicing("auto")
        _emit(f"Enabled attention slicing ({free_mb / 1024:.1f} GB free)")

    _pipe_type = "image"
    _loaded_gpu = gpu_id
    _loaded_model = model_name
    _emit(f"{model_name} ready on GPU {gpu_id} ({strategy})")


def _load_loras(model_cfg, on_progress=None):
    """Load all LoRA adapters specified in a model config."""
    def _emit(msg):
        log.info(msg)
        if on_progress:
            on_progress(msg)

    loras = model_cfg.get("loras", [])
    if not loras:
        return

    adapter_names = []
    adapter_scales = []
    for i, lora in enumerate(loras):
        lora_id = lora["id"]
        adapter_name = f"lora_{i}"
        if not _is_model_cached(lora_id):
            _download_model(lora_id, on_progress=on_progress)
        _emit(f"Loading LoRA: {lora_id}...")
        _pipe.load_lora_weights(
            lora_id,
            weight_name=lora.get("weight_name"),
            adapter_name=adapter_name,
        )
        adapter_names.append(adapter_name)
        adapter_scales.append(lora.get("scale", 1.0))

    _pipe.set_adapters(adapter_names, adapter_weights=adapter_scales)
    _emit(f"Loaded {len(loras)} LoRA adapter(s)")


def _swap_lora(model_name, model_cfg, on_progress=None):
    """Unload current LoRAs and load new ones without restarting."""
    global _loaded_model

    def _emit(msg):
        log.info(msg)
        if on_progress:
            on_progress(msg)

    try:
        _pipe.unload_lora_weights()
        _emit("Unloaded previous LoRA(s)")
    except Exception:
        pass

    _load_loras(model_cfg, on_progress=on_progress)
    _loaded_model = model_name
    _emit(f"Switched to {model_name} on GPU {_loaded_gpu}")


class _ModelSwitchRequired(Exception):
    """Raised when a different model is requested and the server must restart."""
    def __init__(self, current: str, requested: str):
        self.current = current
        self.requested = requested
        super().__init__(f"Model switch required: {current} → {requested}")


def _ensure_image_model(model_name: str | None = None, on_progress=None):
    """Load the requested image model if needed, selecting the best GPU.

    If the requested model is already loaded, reuse it. If a different
    model is loaded, raises ``_ModelSwitchRequired`` — the client will
    kill the server and restart with the new model (NF4 quantized weights
    can't be freed from GPU memory within the same process).
    """
    model_name = model_name or _DEFAULT_MODEL
    if model_name not in _MODELS:
        log.warning("Unknown model %r, falling back to %s", model_name, _DEFAULT_MODEL)
        model_name = _DEFAULT_MODEL
    model_cfg = _MODELS[model_name]

    if _pipe_type == "image" and _pipe is not None and _loaded_model == model_name:
        log.info("Reusing %s on GPU %d", model_name, _loaded_gpu)
        return

    # If audio or video model is loaded, need to switch
    if _pipe_type in ("audio", "video"):
        raise _ModelSwitchRequired(_loaded_model or "unknown", model_name)

    # If the base model is the same, just swap the LoRA instead of restarting
    if (_pipe is not None and _loaded_model
            and _loaded_model != model_name
            and _MODELS[_loaded_model]["model_id"] == model_cfg["model_id"]):
        log.info("Same base model, swapping LoRA: %s → %s", _loaded_model, model_name)
        _swap_lora(model_name, model_cfg, on_progress)
        return

    # A different base model is already loaded — can't switch in-process
    if _pipe is not None and _loaded_model and _loaded_model != model_name:
        raise _ModelSwitchRequired(_loaded_model, model_name)

    if on_progress:
        on_progress("Selecting GPU...")
    gpu_id, free_mb, total_mb = _find_best_gpu()

    _load_image_model(model_name, gpu_id, free_mb, total_mb, on_progress=on_progress)


def _ensure_audio_model(on_progress=None):
    """Load the audio model if needed.

    If the audio model is already loaded, reuse it. If a different
    model type is loaded, raises ``_ModelSwitchRequired``.
    """
    if _pipe_type == "audio" and _pipe is not None:
        log.info("Reusing audio model on GPU %d", _loaded_gpu)
        return

    # If image or video model is loaded, need to switch
    if _pipe_type in ("image", "video"):
        raise _ModelSwitchRequired(_loaded_model or "unknown", "ace-step")

    if on_progress:
        on_progress("Selecting GPU...")

    _load_audio_model(on_progress=on_progress)


def _load_video_model(on_progress=None):
    """Load Wan2.1-T2V-1.3B for video generation."""
    global _pipe, _pipe_type, _loaded_gpu, _loaded_model

    def _emit(msg):
        log.info(msg)
        if on_progress:
            on_progress(msg)

    # If audio or image model is loaded, need to switch
    if _pipe_type in ("audio", "image"):
        raise _ModelSwitchRequired(_loaded_model or "unknown", "wan2.1-t2v")

    _unload()
    log.info("Loading Wan2.1-T2V-1.3B (video)...")
    import torch
    from diffusers import AutoencoderKLWan, WanPipeline
    from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler

    gpu_id, free_mb, _total_mb = _find_best_gpu()
    log.info("Selected GPU %d (%.1f GB free) for video model", gpu_id, free_mb / 1024)

    model_id = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
    vae = AutoencoderKLWan.from_pretrained(
        model_id, subfolder="vae", torch_dtype=torch.float32,
    )
    _pipe = WanPipeline.from_pretrained(
        model_id, vae=vae, torch_dtype=torch.bfloat16,
    )
    _pipe.scheduler = UniPCMultistepScheduler.from_config(
        _pipe.scheduler.config, flow_shift=3.0,
    )
    _pipe.enable_sequential_cpu_offload(gpu_id=gpu_id)
    if hasattr(_pipe, "enable_vae_tiling"):
        _pipe.enable_vae_tiling()
    _pipe_type = "video"
    _loaded_gpu = gpu_id
    _loaded_model = "wan2.1-t2v"
    log.info("Wan2.1-T2V-1.3B ready on GPU %d", gpu_id)


def _load_audio_model(on_progress=None):
    """Load ACE-Step audio generation model for full song generation."""
    global _pipe, _pipe_type, _loaded_gpu, _loaded_model

    def _emit(msg):
        log.info(msg)
        if on_progress:
            on_progress(msg)

    _unload()
    _emit("Loading ACE-Step audio model...")

    import torch
    from diffusers import DiffusionPipeline

    gpu_id, free_mb, _total_mb = _find_best_gpu()
    log.info("Selected GPU %d (%.1f GB free) for audio model", gpu_id, free_mb / 1024)

    model_id = _AUDIO_MODEL["model_id"]

    # Pre-download if not cached
    if not _is_model_cached(model_id):
        _download_model(model_id, on_progress=on_progress)

    with _TqdmProgressForwarder(on_progress, label="Loading audio model"):
        # ACE-Step uses a custom pipeline - load with trust_remote_code
        _pipe = DiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.float16,
            trust_remote_code=True,
        )

    _emit(f"Setting up model offload on GPU {gpu_id}...")
    _pipe.enable_model_cpu_offload(gpu_id=gpu_id)

    _pipe_type = "audio"
    _loaded_gpu = gpu_id
    _loaded_model = "ace-step"
    log.info("ACE-Step audio model ready on GPU %d", gpu_id)


# ── Non-streaming generation (backward-compatible) ────────────────────

def _generate_image(body):
    """Generate an image and return the output path."""
    import torch
    model_name = body.get("model") or _DEFAULT_MODEL
    _ensure_image_model(model_name)
    model_cfg = _MODELS.get(model_name, _MODELS[_DEFAULT_MODEL])
    prompt = body["description"]
    height, width = _SIZE_PRESETS.get(body.get("size", "square"), (1024, 1024))
    torch.cuda.empty_cache()
    pipe_kwargs = dict(
        prompt=prompt,
        num_inference_steps=model_cfg["num_inference_steps"],
        guidance_scale=model_cfg["guidance_scale"],
        height=height,
        width=width,
    )
    with torch.inference_mode():
        image = _pipe(**pipe_kwargs).images[0]
    timestamp = int(time.time() * 1000)
    out_path = f"/home/computron/generated_images/generated_{timestamp}.png"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    image.save(out_path)
    log.info("Image saved: %s", out_path)
    return {"path": out_path}


def _generate_video(body):
    """Generate a video and return the output path."""
    import torch
    from diffusers.utils import export_to_video

    # Check if we need to switch models
    if _pipe_type in ("audio", "image"):
        raise _ModelSwitchRequired(_loaded_model or "unknown", "wan2.1-t2v")

    if _pipe_type != "video":
        _load_video_model()
    prompt = body["description"]
    num_frames = int(body.get("num_frames", 81))
    height = int(body.get("height", 480))
    width = int(body.get("width", 832))

    # Adjust flow_shift based on resolution
    if height >= 720:
        from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler
        _pipe.scheduler = UniPCMultistepScheduler.from_config(
            _pipe.scheduler.config, flow_shift=5.0,
        )

    with torch.inference_mode():
        output = _pipe(
            prompt=prompt,
            height=height,
            width=width,
            num_inference_steps=20,
            num_frames=num_frames,
        )
    frames = output.frames[0]
    timestamp = int(time.time() * 1000)
    out_path = f"/home/computron/generated_videos/generated_{timestamp}.mp4"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    export_to_video(frames, out_path, fps=16)
    log.info("Video saved: %s", out_path)
    return {"path": out_path}


def _generate_audio(body):
    """Generate audio/music using ACE-Step and return the output path.
    
    ACE-Step is a diffusion-based music generation model that can create
    full songs up to 4 minutes in length with natural language prompts.
    """
    import torch
    import scipy.io.wavfile

    _ensure_audio_model()

    prompt = body["description"]
    negative_prompt = body.get("negative_prompt", "")

    # Get duration in seconds (ACE-Step supports up to 4 minutes)
    duration = float(body.get("duration", 30.0))  # Default 30 seconds
    duration = min(duration, _AUDIO_MODEL["max_duration"])  # Cap at max

    # Get generation parameters
    num_inference_steps = int(body.get("steps", _AUDIO_MODEL["num_inference_steps"]))
    guidance_scale = float(body.get("cfg_scale", _AUDIO_MODEL["guidance_scale"]))
    seed = body.get("seed")

    generator = None
    if seed is not None:
        import torch
        generator = torch.Generator(device=f"cuda:{_loaded_gpu}").manual_seed(int(seed))

    with torch.inference_mode():
        output = _pipe(
            prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=num_inference_steps,
            audio_length_in_s=duration,
            num_waveforms_per_prompt=1,
            guidance_scale=guidance_scale,
            generator=generator,
        )

    audio = output.audios[0]
    sample_rate = _AUDIO_MODEL["sample_rate"]

    timestamp = int(time.time() * 1000)
    out_path = f"/home/computron/generated_audio/generated_{timestamp}.wav"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Save as WAV file (scipy expects int16 format)
    audio_int16 = (audio * 32767).astype("int16")
    scipy.io.wavfile.write(out_path, sample_rate, audio_int16)

    log.info("Audio saved: %s (%.1fs, %d Hz)", out_path, duration, sample_rate)
    return {"path": out_path, "duration": duration, "sample_rate": sample_rate}


# ── Streaming generation (with progress + previews) ───────────────────

def _generate_image_stream(body, write_line):
    """Generate an image with streaming progress and optional TAESD previews."""
    import torch

    model_name = body.get("model") or _DEFAULT_MODEL
    model_cfg = _MODELS.get(model_name, _MODELS[_DEFAULT_MODEL])
    total_steps = model_cfg["num_inference_steps"]
    use_preview = model_cfg["taesd_preview"]

    def _loading_progress(msg):
        write_line({"status": "loading", "message": msg})

    _loading_progress(f"Preparing {model_name}...")
    _ensure_image_model(model_name, on_progress=_loading_progress)

    if use_preview:
        _ensure_taesd()

    prompt = body["description"]
    height, width = _SIZE_PRESETS.get(body.get("size", "square"), (1024, 1024))

    torch.cuda.empty_cache()
    write_line({"status": "generating", "step": 0, "total_steps": total_steps,
                "message": "Starting image generation..."})

    def on_step_end(pipe, step_index, timestep, callback_kwargs):
        preview = None
        if use_preview:
            latents = callback_kwargs.get("latents")
            preview = _decode_preview_taesd(latents, height=height, width=width)
        write_line({
            "status": "generating",
            "step": step_index + 1,
            "total_steps": total_steps,
            "preview": preview,
            "message": f"Step {step_index + 1}/{total_steps}",
        })
        return callback_kwargs

    pipe_kwargs = dict(
        prompt=prompt,
        num_inference_steps=total_steps,
        guidance_scale=model_cfg["guidance_scale"],
        height=height,
        width=width,
        callback_on_step_end=on_step_end,
    )
    with torch.inference_mode():
        image = _pipe(**pipe_kwargs).images[0]

    timestamp = int(time.time() * 1000)
    out_path = f"/home/computron/generated_images/generated_{timestamp}.png"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    image.save(out_path)
    log.info("Image saved: %s", out_path)

    write_line({"status": "complete", "path": out_path})


def _generate_video_stream(body, write_line):
    """Generate a video with streaming progress and periodic first-frame previews."""
    import torch
    from diffusers.utils import export_to_video

    # Check if we need to switch models
    if _pipe_type in ("audio", "image"):
        write_line({"status": "restart_required", "model": "wan2.1-t2v"})
        threading.Thread(target=_shutdown, daemon=True).start()
        return

    if _pipe_type != "video":
        write_line({"status": "loading", "message": "Loading Wan2.1-T2V-1.3B..."})
        _load_video_model(on_progress=lambda msg: write_line({"status": "loading", "message": msg}))

    prompt = body["description"]
    num_frames = int(body.get("num_frames", 81))
    height = int(body.get("height", 480))
    width = int(body.get("width", 832))
    total_steps = 20

    if height >= 720:
        from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler
        _pipe.scheduler = UniPCMultistepScheduler.from_config(
            _pipe.scheduler.config, flow_shift=5.0,
        )

    write_line({"status": "generating", "step": 0, "total_steps": total_steps,
                "message": "Starting video generation..."})

    def on_step_end(pipe, step_index, timestep, callback_kwargs):
        step_num = step_index + 1
        preview = None
        # Decode first frame preview at periodic intervals
        if step_num in _VIDEO_PREVIEW_STEPS:
            latents = callback_kwargs.get("latents")
            if latents is not None:
                preview = _decode_video_first_frame(latents)
        write_line({
            "status": "generating",
            "step": step_num,
            "total_steps": total_steps,
            "preview": preview,
            "message": f"Step {step_num}/{total_steps}",
        })
        return callback_kwargs

    with torch.inference_mode():
        output = _pipe(
            prompt=prompt,
            height=height,
            width=width,
            num_inference_steps=total_steps,
            num_frames=num_frames,
            callback_on_step_end=on_step_end,
        )

    frames = output.frames[0]
    timestamp = int(time.time() * 1000)
    out_path = f"/home/computron/generated_videos/generated_{timestamp}.mp4"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    export_to_video(frames, out_path, fps=16)
    log.info("Video saved: %s", out_path)

    write_line({"status": "complete", "path": out_path})


def _generate_audio_stream(body, write_line):
    """Generate audio with streaming progress using ACE-Step.
    
    ACE-Step is a diffusion-based model for full song generation.
    """
    import torch
    import scipy.io.wavfile

    def _loading_progress(msg):
        write_line({"status": "loading", "message": msg})

    _loading_progress("Preparing ACE-Step audio model...")
    _ensure_audio_model(on_progress=_loading_progress)

    prompt = body["description"]
    negative_prompt = body.get("negative_prompt", "")

    # Get duration in seconds (ACE-Step supports up to 4 minutes)
    duration = float(body.get("duration", 30.0))
    duration = min(duration, _AUDIO_MODEL["max_duration"])

    num_inference_steps = int(body.get("steps", _AUDIO_MODEL["num_inference_steps"]))
    guidance_scale = float(body.get("cfg_scale", _AUDIO_MODEL["guidance_scale"]))
    seed = body.get("seed")

    generator = None
    if seed is not None:
        generator = torch.Generator(device=f"cuda:{_loaded_gpu}").manual_seed(int(seed))

    write_line({"status": "generating", "step": 0, "total_steps": num_inference_steps,
                "message": f"Starting audio generation ({duration:.1f}s)..."})

    # Note: ACE-Step may not have step callbacks, emit start/complete
    with torch.inference_mode():
        output = _pipe(
            prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=num_inference_steps,
            audio_length_in_s=duration,
            num_waveforms_per_prompt=1,
            guidance_scale=guidance_scale,
            generator=generator,
        )

    audio = output.audios[0]
    sample_rate = _AUDIO_MODEL["sample_rate"]

    timestamp = int(time.time() * 1000)
    out_path = f"/home/computron/generated_audio/generated_{timestamp}.wav"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    audio_int16 = (audio * 32767).astype("int16")
    scipy.io.wavfile.write(out_path, sample_rate, audio_int16)

    log.info("Audio saved: %s (%.1fs, %d Hz)", out_path, duration, sample_rate)
    write_line({"status": "complete", "path": out_path, "duration": duration, "sample_rate": sample_rate})


# ── HTTP handler ──────────────────────────────────────────────────────
class _ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    allow_reuse_port = True
    daemon_threads = True


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access logs

    def do_GET(self):
        if self.path == "/health":
            self._json_response(200, {
                "status": "ok",
                "model": _pipe_type,
                "model_name": _loaded_model,
                "available_models": list(_MODELS.keys()),
            })
        else:
            self.send_error(404)

    def do_POST(self):
        global _last_request
        _last_request = time.time()

        if self.path == "/shutdown":
            self._json_response(200, {"status": "shutting_down"})
            threading.Thread(target=_shutdown, daemon=True).start()
            return

        if self.path == "/generate":
            self._handle_generate()
            return

        if self.path == "/generate-stream":
            self._handle_generate_stream()
            return

        self.send_error(404)

    def _handle_generate(self):
        """Non-streaming generation (backward-compatible)."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError) as exc:
            self._json_response(400, {"error": str(exc)})
            return

        gen_type = body.get("type")
        if gen_type not in ("image", "video", "audio"):
            self._json_response(400, {"error": "type must be 'image', 'video', or 'audio'"})
            return

        with _lock:
            try:
                if gen_type == "image":
                    result = _generate_image(body)
                elif gen_type == "video":
                    result = _generate_video(body)
                else:
                    result = _generate_audio(body)
                self._json_response(200, result)
            except _ModelSwitchRequired:
                self._json_response(409, {"restart_required": True,
                                          "model": body.get("model")})
                threading.Thread(target=_shutdown, daemon=True).start()
            except Exception as exc:
                log.exception("Generation failed")
                self._json_response(500, {"error": str(exc)})

    def _handle_generate_stream(self):
        """Streaming generation with progress and previews via chunked JSONL."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError) as exc:
            self._json_response(400, {"error": str(exc)})
            return

        gen_type = body.get("type")
        if gen_type not in ("image", "video", "audio"):
            self._json_response(400, {"error": "type must be 'image', 'video', or 'audio'"})
            return

        # Start chunked response
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def write_line(data):
            """Write a JSONL line using HTTP chunked encoding."""
            line = json.dumps(data, separators=(",", ":")) + "\n"
            chunk = line.encode("utf-8")
            # Chunked transfer: hex size + CRLF + data + CRLF
            self.wfile.write(f"{len(chunk):x}\r\n".encode())
            self.wfile.write(chunk)
            self.wfile.write(b"\r\n")
            self.wfile.flush()

        with _lock:
            try:
                if gen_type == "image":
                    _generate_image_stream(body, write_line)
                elif gen_type == "video":
                    _generate_video_stream(body, write_line)
                else:
                    _generate_audio_stream(body, write_line)
            except _ModelSwitchRequired as exc:
                write_line({"status": "restart_required",
                            "model": exc.requested})
                threading.Thread(target=_shutdown, daemon=True).start()
            except Exception as exc:
                log.exception("Streaming generation failed")
                write_line({"status": "failed", "message": str(exc)})

        # Terminate chunked transfer
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _json_response(self, code, data):
        payload = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


# ── Server lifecycle ──────────────────────────────────────────────────
_server = None


def _shutdown():
    """Gracefully shut down the server."""
    time.sleep(0.2)  # let response flush
    log.info("Shutting down...")
    _unload()
    if _server:
        _server.shutdown()
    _cleanup_pid()
    sys.exit(0)


def _cleanup_pid():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def _idle_watchdog():
    """Background thread that shuts down the server after IDLE_TIMEOUT."""
    while True:
        time.sleep(30)
        if time.time() - _last_request > IDLE_TIMEOUT:
            log.info("Idle timeout reached (%ds), shutting down", IDLE_TIMEOUT)
            _shutdown()


def main():
    global _server

    # Log available GPUs at startup (selection happens per-job)
    gpu_id, free_mb, total_mb = _find_best_gpu()
    log.info("Startup: best GPU is %d (%.1f GB free / %.1f GB total), will re-evaluate per job",
             gpu_id, free_mb / 1024, total_mb / 1024)

    # Write PID file
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    signal.signal(signal.SIGTERM, lambda *_: _shutdown())
    signal.signal(signal.SIGINT, lambda *_: _shutdown())

    # Start idle watchdog
    watchdog = threading.Thread(target=_idle_watchdog, daemon=True)
    watchdog.start()

    _server = _ReusableHTTPServer(("127.0.0.1", PORT), _Handler)
    log.info("Inference server listening on port %d (PID %d)", PORT, os.getpid())
    try:
        _server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _cleanup_pid()


if __name__ == "__main__":
    main()
