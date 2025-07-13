# Standard library imports
"""aiohttp web server exposing the COMPUTRON_9000 agent API."""

import json
import logging
from pathlib import Path
from typing import Any

# Third-party imports
from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response, StreamResponse
from pydantic import BaseModel, ValidationError

from agents.ollama import handle_user_message
from agents.types import Data

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


class ChatRequest(BaseModel):
    message: str
    data: list[dict[str, Any]] | None = None


def _guess_content_type(file_path: str) -> str:
    """
    Guess the content type based on file extension.

    Args:
        file_path (str): The file path.

    Returns:
        str: The content type.
    """
    if file_path.endswith(".css"):
        return "text/css"
    if file_path.endswith(".js"):
        return "application/javascript"
    if file_path.endswith(".html"):
        return "text/html"
    if file_path.endswith(".png"):
        return "image/png"
    if file_path.endswith(".jpg") or file_path.endswith(".jpeg"):
        return "image/jpeg"
    if file_path.endswith(".svg"):
        return "image/svg+xml"
    return "application/octet-stream"


async def handle_options(_request: Request) -> Response:
    """
    Handle CORS preflight requests.

    Args:
        request (Request): The incoming request.

    Returns:
        Response: The HTTP response.
    """
    return web.Response(status=200, headers=CORS_HEADERS)


async def handle_post(request: Request) -> StreamResponse:
    """
    Handle chat POST requests from the UI.

    Args:
        request (Request): The incoming request.

    Returns:
        StreamResponse: The streaming HTTP response.
    """
    if request.path == "/api/chat":
        try:
            body = await request.text()
            try:
                data = ChatRequest.model_validate_json(body)
            except ValidationError as ve:
                logger.warning(f"Invalid request data: {ve}")
                return web.json_response(
                    {"error": "Invalid JSON or missing required fields."},
                    status=400,
                    headers=CORS_HEADERS,
                )
        except Exception:
            logger.exception("Failed to parse request JSON")
            return web.json_response(
                {"error": "Invalid JSON."}, status=400, headers=CORS_HEADERS
            )
        user_query = data.message.strip()
        if not user_query:
            return web.json_response(
                {"error": "Message field is required."},
                status=400,
                headers=CORS_HEADERS,
            )
        # Handle optional data field (array with 0 or more entries, always with base64 and content_type)
        data_objs = None
        if data.data and len(data.data) > 0:
            try:
                data_objs = [
                    Data(base64_encoded=obj["base64"], content_type=obj["content_type"])
                    for obj in data.data
                ]
            except Exception as exc:
                logger.warning(f"Invalid data field: {exc}")
                return web.json_response(
                    {"error": "Invalid data field."}, status=400, headers=CORS_HEADERS
                )
        resp = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "application/json",
                **CORS_HEADERS,
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
            },
        )
        await resp.prepare(request)
        try:
            async for event in handle_user_message(user_query, data_objs):
                data_out = {
                    "response": event.message,
                    "final": event.final,
                    "thinking": event.thinking,
                }
                await resp.write((json.dumps(data_out) + "\n").encode("utf-8"))
                if event.final:
                    break
        except Exception as exc:
            logger.exception("Error in handle_user_message")
            error_data = {"error": f"Server error: {str(exc)}", "final": True}
            await resp.write((json.dumps(error_data) + "\n").encode("utf-8"))
        finally:
            await resp.write_eof()
        return resp
    return web.Response(status=404)


async def handle_get(request: Request) -> Response:
    """
    Serve the chat UI and static assets.

    Args:
        request (Request): The incoming request.

    Returns:
        Response: The HTTP response.
    """
    if request.path in ["", "/"]:
        html_path = STATIC_DIR / "agent_ui.html"
        if html_path.is_file():
            with html_path.open("rb") as f:
                html = f.read()
            return web.Response(
                body=html, content_type="text/html", headers=CORS_HEADERS
            )
        logger.warning(f"File not found: {html_path}")
        return web.Response(
            text="<h1>File not found</h1>",
            content_type="text/html",
            headers=CORS_HEADERS,
        )
    if request.path.startswith("/static/"):
        rel_path = request.path[len("/static/") :]
        file_path = STATIC_DIR / rel_path
        if file_path.is_file():
            content_type = _guess_content_type(str(file_path))
            with file_path.open("rb") as f:
                data = f.read()
            return web.Response(
                body=data, content_type=content_type, headers=CORS_HEADERS
            )
        logger.warning(f"Static file not found: {file_path}")
        return web.Response(status=404)
    return web.Response(status=404)


# Set client_max_size to 10 MB (adjust as needed)
app = web.Application(client_max_size=10 * 1024**2)
app.router.add_route("OPTIONS", "/api/chat", handle_options)
app.router.add_route("POST", "/api/chat", handle_post)
app.router.add_route("GET", "/", handle_get)
app.router.add_route("GET", "/static/{tail:.*}", handle_get)
