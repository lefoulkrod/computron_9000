"""Shared HTTP helpers for integration route handlers."""

from __future__ import annotations

from typing import Any

from aiohttp import web

ERROR_STATUS = {
    "BAD_REQUEST": 400,
    "NOT_FOUND": 404,
    "AUTH": 409,           # credentials rejected by upstream — client can reconnect
    "WRITE_DENIED": 403,
    "UPSTREAM": 502,
    "INTERNAL": 500,
}


def error_response(code: str, message: str) -> web.Response:
    """Map a supervisor/broker error code to an HTTP response."""
    status = ERROR_STATUS.get(code, 500)
    return web.json_response(
        {"error": {"code": code, "message": message}}, status=status,
    )
