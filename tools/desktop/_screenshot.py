"""Screenshot capture from the desktop environment."""

import asyncio
import logging

from podman import PodmanClient

from config import load_config

logger = logging.getLogger(__name__)


async def capture_screenshot() -> bytes:
    """Capture a screenshot of the desktop and return raw JPEG bytes.

    Returns:
        Raw JPEG image bytes.

    Raises:
        RuntimeError: If the screenshot capture fails.
    """
    config = load_config()
    container_name = config.virtual_computer.container_name
    container_user = config.virtual_computer.container_user
    quality = config.desktop.screenshot_quality
    display = config.desktop.display

    loop = asyncio.get_running_loop()

    def _capture_sync() -> bytes:
        client = PodmanClient().from_env()
        containers = client.containers.list()
        container = next(
            (c for c in containers if c.name == container_name), None,
        )
        if container is None:
            msg = "Container '%s' not found" % container_name
            raise RuntimeError(msg)

        # Use ImageMagick's import command to capture the root window as JPEG
        cmd = (
            "export DISPLAY=%s; "
            "import -window root -quality %d jpeg:-"
        ) % (display, quality)

        exit_code, output = container.exec_run(
            ["bash", "-c", cmd],
            user=container_user,
        )
        if exit_code != 0:
            msg = "Screenshot capture failed with exit code %d" % exit_code
            raise RuntimeError(msg)

        return output

    try:
        return await loop.run_in_executor(None, _capture_sync)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("Failed to capture desktop screenshot")
        raise RuntimeError("Screenshot capture failed: %s" % exc) from exc
