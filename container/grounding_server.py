"""Persistent grounding server for desktop UI element location.

Keeps UI-TARS loaded in VRAM between requests. Auto-shuts down after
3 minutes of inactivity to free VRAM for other workloads.

Usage (inside container):
    python3 /opt/inference/grounding_server.py &

Protocol:
    POST /ground   — JSON body with screenshot + task, returns action + coords
    GET  /health   — returns {"status": "ok"}
    POST /shutdown — graceful shutdown
"""

import base64
import io
import json
import logging
import math
import os
import re
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

if not os.environ.get("HF_TOKEN"):
    _token_path = os.path.expanduser("~/.cache/huggingface/token")
    if os.path.isfile(_token_path):
        with open(_token_path) as _f:
            _tok = _f.read().strip()
            if _tok:
                os.environ["HF_TOKEN"] = _tok

PORT = 18902
PID_FILE = "/tmp/grounding_server.pid"
IDLE_TIMEOUT = 180  # 3 minutes

MODEL_ID = "ByteDance-Seed/UI-TARS-1.5-7B"

logging.basicConfig(
    level=logging.INFO,
    format="[grounding] %(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("grounding")

# ── Coordinate conversion ─────────────────────────────────────────────

_IMAGE_FACTOR = 28
_MIN_PIXELS = 100 * 28 * 28
_MAX_PIXELS = 16384 * 28 * 28


def _smart_resize(height, width):
    """Replicate the Qwen2.5-VL processor's internal resize logic."""
    h = max(_IMAGE_FACTOR, round(height / _IMAGE_FACTOR) * _IMAGE_FACTOR)
    w = max(_IMAGE_FACTOR, round(width / _IMAGE_FACTOR) * _IMAGE_FACTOR)
    if h * w > _MAX_PIXELS:
        beta = math.sqrt((height * width) / _MAX_PIXELS)
        h = math.floor(height / beta / _IMAGE_FACTOR) * _IMAGE_FACTOR
        w = math.floor(width / beta / _IMAGE_FACTOR) * _IMAGE_FACTOR
    elif h * w < _MIN_PIXELS:
        beta = math.sqrt(_MIN_PIXELS / (height * width))
        h = math.ceil(height * beta / _IMAGE_FACTOR) * _IMAGE_FACTOR
        w = math.ceil(width * beta / _IMAGE_FACTOR) * _IMAGE_FACTOR
    return h, w


def _convert_coords(model_output, orig_width, orig_height):
    """Parse coordinate pairs from model output and convert to screen space."""
    resized_h, resized_w = _smart_resize(orig_height, orig_width)
    results = []
    for match in re.finditer(r"\((\d+),(\d+)\)", model_output):
        mx, my = int(match.group(1)), int(match.group(2))
        screen_x = int((mx / resized_w) * orig_width)
        screen_y = int((my / resized_h) * orig_height)
        results.append({"model": [mx, my], "screen": [screen_x, screen_y]})
    return results


# ── UI-TARS system prompt ─────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

## Action Space

click(start_box='<|box_start|>(x1,y1)<|box_end|>')
left_double(start_box='<|box_start|>(x1,y1)<|box_end|>')
right_single(start_box='<|box_start|>(x1,y1)<|box_end|>')
drag(start_box='<|box_start|>(x1,y1)<|box_end|>', end_box='<|box_start|>(x3,y3)<|box_end|>')
hotkey(key='')
type(content='')
scroll(start_box='<|box_start|>(x1,y1)<|box_end|>', direction='down|up|right|left')
wait()
finished(content='')

## Notes
- Use English in the Thought part.
- Write a small plan and summarize the next action in one sentence in the Thought part.
"""

# ── Model state ───────────────────────────────────────────────────────

_model = None
_processor = None
_lock = threading.Lock()
_last_request_time = time.time()


def _select_gpu():
    """Pick the best GPU — the one with the most free VRAM."""
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True,
        )
        best_idx, best_free = 0, 0
        for line in result.stdout.strip().split("\n"):
            parts = line.split(",")
            idx, free = int(parts[0].strip()), int(parts[1].strip())
            if free > best_free:
                best_idx, best_free = idx, free
        log.info("Selected GPU %d with %d MiB free", best_idx, best_free)
        return best_idx
    except Exception:
        log.warning("Could not query GPUs, defaulting to GPU 0")
        return 0


def _load_model():
    """Load UI-TARS model and processor into VRAM."""
    global _model, _processor
    import torch
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    gpu_idx = _select_gpu()
    torch.cuda.set_device(gpu_idx)
    device = "cuda:%d" % gpu_idx

    log.info("Loading %s onto %s (4-bit quantized) ...", MODEL_ID, device)
    t0 = time.time()

    from transformers import BitsAndBytesConfig

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
    )

    _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_ID,
        quantization_config=quantization_config,
        device_map=device,
    )
    _processor = AutoProcessor.from_pretrained(MODEL_ID)
    log.info("Model loaded in %.1fs (~4-bit, single GPU)", time.time() - t0)


def _run_inference(image_bytes, task):
    """Run grounding inference and return raw model output + image dimensions."""
    import torch
    from PIL import Image

    global _last_request_time
    _last_request_time = time.time()

    img = Image.open(io.BytesIO(image_bytes))
    orig_w, orig_h = img.size

    messages = [
        {"role": "system", "content": [{"type": "text", "text": _SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": img},
                {"type": "text", "text": task},
            ],
        },
    ]

    text = _processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
    )
    inputs = _processor(
        text=[text],
        images=[img],
        padding=True,
        return_tensors="pt",
    ).to(_model.device)

    with torch.no_grad():
        generated_ids = _model.generate(**inputs, max_new_tokens=256)

    trimmed = [
        out[len(inp):] for inp, out in zip(inputs.input_ids, generated_ids)
    ]
    output = _processor.batch_decode(
        trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False,
    )[0]

    return output, orig_w, orig_h


def _parse_action(raw_output, orig_w, orig_h):
    """Parse the model output into a structured action dict."""
    # Extract thought and action parts
    thought = ""
    action_text = raw_output.strip()

    if "Thought:" in raw_output and "Action:" in raw_output:
        parts = raw_output.split("Action:", 1)
        thought = parts[0].replace("Thought:", "").strip()
        action_text = parts[1].strip()
    elif "Action:" in raw_output:
        action_text = raw_output.split("Action:", 1)[1].strip()

    # Parse action type
    action_match = re.match(r"(\w+)\(", action_text)
    action_type = action_match.group(1) if action_match else "unknown"

    # Convert coordinates to screen space
    coords = _convert_coords(action_text, orig_w, orig_h)

    result = {
        "thought": thought,
        "action": action_text,
        "action_type": action_type,
        "raw": raw_output,
    }

    if coords:
        result["coordinates"] = coords
        # Convenience: primary click target
        result["x"] = coords[0]["screen"][0]
        result["y"] = coords[0]["screen"][1]

    # Extract typed content for type() actions
    type_match = re.search(r"type\(content='([^']*)'\)", action_text)
    if type_match:
        result["type_content"] = type_match.group(1)

    # Extract hotkey for hotkey() actions
    hotkey_match = re.search(r"hotkey\(key='([^']*)'\)", action_text)
    if hotkey_match:
        result["hotkey"] = hotkey_match.group(1)

    # Extract scroll direction
    scroll_match = re.search(r"direction='(\w+)'", action_text)
    if scroll_match:
        result["scroll_direction"] = scroll_match.group(1)

    # Extract finished content
    finished_match = re.search(r"finished\(content='([^']*)'\)", action_text)
    if finished_match:
        result["finished_content"] = finished_match.group(1)

    return result


# ── HTTP handler ──────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info(fmt, *args)

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json_response({"status": "ok", "model": MODEL_ID})
        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/ground":
            self._handle_ground()
        elif self.path == "/shutdown":
            self._json_response({"status": "shutting_down"})
            threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0))).start()
        else:
            self._json_response({"error": "not found"}, 404)

    def _handle_ground(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError) as exc:
            self._json_response({"error": "Invalid JSON: %s" % exc}, 400)
            return

        image_b64 = body.get("image")
        task = body.get("task", "")
        if not image_b64:
            self._json_response({"error": "Missing 'image' field"}, 400)
            return
        if not task:
            self._json_response({"error": "Missing 'task' field"}, 400)
            return

        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception:
            self._json_response({"error": "Invalid base64 image"}, 400)
            return

        with _lock:
            try:
                raw_output, orig_w, orig_h = _run_inference(image_bytes, task)
                result = _parse_action(raw_output, orig_w, orig_h)
                result["image_size"] = [orig_w, orig_h]
                self._json_response(result)
            except Exception as exc:
                log.exception("Inference failed")
                self._json_response({"error": str(exc)}, 500)


# ── Idle watchdog ─────────────────────────────────────────────────────

def _idle_watchdog():
    """Shut down if no requests received within IDLE_TIMEOUT."""
    while True:
        time.sleep(30)
        idle = time.time() - _last_request_time
        if idle > IDLE_TIMEOUT:
            log.info("Idle for %.0fs, shutting down to free VRAM", idle)
            os._exit(0)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    # Write PID file
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    signal.signal(signal.SIGTERM, lambda *_: os._exit(0))

    _load_model()

    # Start idle watchdog
    wd = threading.Thread(target=_idle_watchdog, daemon=True)
    wd.start()

    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    log.info("Grounding server listening on port %d", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            os.remove(PID_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
