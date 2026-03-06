# Container Scripts

Scripts in this directory run **inside** the Podman container (`computron_virtual_computer`), not on the host.

## Files

| File | Description |
|------|-------------|
| `Dockerfile` | Container image definition (CUDA, Python, Node, ML stack) |
| `inference_server.py` | Persistent HTTP server that keeps ML models loaded in VRAM between requests. Supports both blocking (`/generate`) and streaming (`/generate-stream`) endpoints with TAESD preview decoding. Auto-shuts down after 10 minutes idle. |
| `inference_client.py` | Thin client that auto-starts the server and provides `generate()` and `generate_stream()` functions for use by custom tools and the `generate_media` host tool. |

## How they get into the container

The container home directory (`~/.computron_9000/container_home/`) is volume-mounted at `/home/computron/` inside the container. When you run `just container-start`:

- **Inference scripts** (`inference_server.py`, `inference_client.py`) are copied to `/opt/inference/` inside the container — outside the agent's sandboxed home directory, so agents can't read or modify them.
- **Other scripts** are copied to the agent's home directory as usual.

## Rebuilding

```bash
just container-build   # rebuild the image from container/Dockerfile
just container-start   # start container + sync scripts
```
