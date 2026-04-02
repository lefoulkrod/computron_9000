"""API route handlers for the compaction eval app."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web

from conversations import list_summary_records, load_summary_record
from sdk.providers._ollama import OllamaProvider

from . import _llm
from ._serialization import serialize_messages

logger = logging.getLogger(__name__)


def _get_provider(request: web.Request) -> OllamaProvider:
    return request.app["provider"]


def _parse_options(body: dict[str, Any]) -> dict[str, Any] | None:
    """Extract Ollama options dict from request body."""
    opts: dict[str, Any] = {}
    for key in ("num_ctx", "num_predict", "temperature", "top_k", "top_p"):
        if key in body:
            opts[key] = body[key]
    return opts or None


# -- Data browsing ----------------------------------------------------------


async def list_records(request: web.Request) -> web.Response:
    """List all compaction records, optionally filtered by conversation_id."""
    conversation_id = request.query.get("conversation_id")
    records = list_summary_records(conversation_id)
    items = [
        {
            "id": r.id,
            "conversation_id": r.conversation_id,
            "agent_name": r.agent_name,
            "source_history": r.source_history,
            "created_at": r.created_at,
            "fill_ratio": round(r.fill_ratio, 3),
            "model": r.model,
            "messages_compacted": r.messages_compacted,
            "input_char_count": r.input_char_count,
            "summary_char_count": r.summary_char_count,
            "elapsed_seconds": r.elapsed_seconds,
        }
        for r in records
    ]
    return web.json_response(items)


async def get_record(request: web.Request) -> web.Response:
    """Get full record detail including source messages and summary."""
    conversation_id = request.match_info["conversation_id"]
    record_id = request.match_info["record_id"]
    record = load_summary_record(conversation_id, record_id)
    if record is None:
        return web.json_response({"error": "Record not found"}, status=404)

    serialized = serialize_messages(record.input_messages)
    data = record.model_dump()
    data["serialized_input"] = serialized
    return web.json_response(data)


async def list_models(request: web.Request) -> web.Response:
    """List available Ollama models."""
    provider = _get_provider(request)
    try:
        models = await provider.list_models()
    except Exception:
        logger.exception("Failed to list models")
        return web.json_response({"error": "Failed to list models"}, status=502)
    return web.json_response({"models": models})


# -- LLM operations ---------------------------------------------------------


async def extract_facts(request: web.Request) -> web.Response:
    """Extract facts from source messages and check which survived."""
    body = await request.json()
    record = load_summary_record(body["conversation_id"], body["record_id"])
    if record is None:
        return web.json_response({"error": "Record not found"}, status=404)

    result = await _llm.extract_facts(
        provider=_get_provider(request),
        model=body["model"],
        input_messages=record.input_messages,
        summary_text=body.get("summary_text") or record.summary_text,
        options=_parse_options(body),
    )
    return web.json_response(result)


async def judge(request: web.Request) -> web.Response:
    """LLM-as-judge scoring."""
    body = await request.json()
    record = load_summary_record(body["conversation_id"], body["record_id"])
    if record is None:
        return web.json_response({"error": "Record not found"}, status=404)

    result = await _llm.judge_summary(
        provider=_get_provider(request),
        model=body["model"],
        input_messages=record.input_messages,
        summary_text=body.get("summary_text") or record.summary_text,
        options=_parse_options(body),
    )
    return web.json_response(result)


async def recompact_handler(request: web.Request) -> web.Response:
    """Re-run compaction with different params."""
    body = await request.json()
    record = load_summary_record(body["conversation_id"], body["record_id"])
    if record is None:
        return web.json_response({"error": "Record not found"}, status=404)

    result = await _llm.recompact(
        provider=_get_provider(request),
        model=body["model"],
        input_messages=record.input_messages,
        prior_summary=record.prior_summary,
        options=_parse_options(body),
        custom_prompt=body.get("custom_prompt"),
        objective=body.get("objective", ""),
    )
    return web.json_response(result)


async def continuation_probe(request: web.Request) -> web.Response:
    """Generate probe questions and test recall."""
    body = await request.json()
    record = load_summary_record(body["conversation_id"], body["record_id"])
    if record is None:
        return web.json_response({"error": "Record not found"}, status=404)

    result = await _llm.continuation_probe(
        provider=_get_provider(request),
        model=body["model"],
        input_messages=record.input_messages,
        summary_text=body.get("summary_text") or record.summary_text,
        options=_parse_options(body),
    )
    return web.json_response(result)


def register_routes(app: web.Application) -> None:
    """Register all routes on the app."""
    app.router.add_get("/api/records", list_records)
    app.router.add_get(
        "/api/records/{conversation_id}/{record_id}", get_record,
    )
    app.router.add_get("/api/models", list_models)
    app.router.add_post("/api/extract-facts", extract_facts)
    app.router.add_post("/api/judge", judge)
    app.router.add_post("/api/recompact", recompact_handler)
    app.router.add_post("/api/continuation-probe", continuation_probe)
