"""Google web search tool built on the Google REST API."""

from __future__ import annotations

import json
import logging
import os
from html import unescape
from typing import Any

import aiohttp
from aiohttp import ClientError
from pydantic import BaseModel, Field, ValidationError

from config import load_config

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
_MAX_PAGE_SIZE = 10


class GoogleSearchInput(BaseModel):
    """Input model for Google search requests."""

    query: str = Field(..., min_length=1)
    max_results: int = 5


class GoogleSearchResult(BaseModel):
    """Output model for a single Google search result."""

    title: str
    link: str
    snippet: str = ""


class GoogleSearchResults(BaseModel):
    """Container for all Google search results."""

    results: list[GoogleSearchResult]


class GoogleSearchError(Exception):
    """Custom exception raised for Google search failures."""


def _normalize_text(value: object) -> str:
    """Return a trimmed string value from ``value`` if possible."""
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_snippet(item: dict[str, Any]) -> str:
    """Extract and clean the snippet text from a result item."""
    for key in ("snippet", "htmlSnippet"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(unescape(value).split())
    return ""


def _extract_message_from_error(error: dict[str, Any]) -> str | None:
    """Pull a human readable message from a Google API error payload."""
    message = error.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()

    errors = error.get("errors")
    if isinstance(errors, list):
        for entry in errors:
            if isinstance(entry, dict):
                entry_message = entry.get("message")
                if isinstance(entry_message, str) and entry_message.strip():
                    return entry_message.strip()
    return None


def _extract_error_message(raw: str) -> str:
    """Parse error information from a raw HTTP response body."""
    stripped = raw.strip()
    if not stripped:
        return "Unknown error"

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = _extract_message_from_error(error)
            if message:
                return message
        for key in ("error_description", "message"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return stripped or "Unknown error"


def _error_message_from_payload(payload: dict[str, Any]) -> str | None:
    """Extract an error message from a successful JSON payload, if present."""
    if not isinstance(payload, dict):
        return None

    error = payload.get("error")
    if isinstance(error, dict):
        return _extract_message_from_error(error)
    return None


def _next_start_index(payload: dict[str, Any]) -> int | None:
    """Return the next start index for pagination if provided by the API."""
    queries = payload.get("queries")
    if not isinstance(queries, dict):
        return None

    next_page = queries.get("nextPage")
    if not isinstance(next_page, list) or not next_page:
        return None

    first = next_page[0]
    if not isinstance(first, dict):
        return None

    start_index = first.get("startIndex")
    if isinstance(start_index, int):
        return start_index
    if isinstance(start_index, str):
        try:
            return int(start_index)
        except ValueError:
            return None
    return None


def _coerce_timeout(timeout_ms: int) -> float:
    """Convert a millisecond timeout to seconds for ``aiohttp``."""
    if timeout_ms <= 0:
        return 10.0
    return max(timeout_ms / 1000.0, 1.0)


async def _perform_request(
    session: aiohttp.ClientSession,
    endpoint: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Perform a single Google Search API request."""
    try:
        async with session.get(endpoint, params=params) as response:
            body = await response.text()
            logger.debug(
                "Google Search API responded with status %s",
                response.status,
            )
            if response.status != 200:
                message = _extract_error_message(body)
                msg = f"Google Search API returned status {response.status}: {message}"
                raise GoogleSearchError(msg)

            try:
                payload: dict[str, Any] = json.loads(body)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
                logger.exception("Invalid JSON received from Google Search API")
                msg = "Google Search API returned invalid JSON"
                raise GoogleSearchError(msg) from exc

            error_message = _error_message_from_payload(payload)
            if error_message:
                raise GoogleSearchError(error_message)

            return payload
    except TimeoutError as exc:
        logger.exception("Google Search API request timed out")
        msg = "Google Search API request timed out"
        raise GoogleSearchError(msg) from exc
    except ClientError as exc:
        logger.exception("Error communicating with Google Search API")
        msg = f"Error communicating with Google Search API: {exc}"
        raise GoogleSearchError(msg) from exc


async def search_google(query: str, max_results: int = 5) -> GoogleSearchResults:
    """Search Google using the REST API and return the top results."""
    try:
        validated = GoogleSearchInput(query=query, max_results=max_results)
    except ValidationError as exc:
        logger.exception("Invalid Google search input")
        msg = f"Invalid input: {exc}"
        raise GoogleSearchError(msg) from exc

    if validated.max_results <= 0:
        logger.debug("Max results <= 0, returning empty result set for query '%s'", query)
        return GoogleSearchResults(results=[])

    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    if not api_key:
        msg = (
            "Google Search API key not configured. Set the GOOGLE_SEARCH_API_KEY environment "
            "variable."
        )
        logger.error(msg)
        raise GoogleSearchError(msg)

    config = load_config()
    tool_config = config.tools.web.search_google

    endpoint = getattr(tool_config, "api_endpoint", _DEFAULT_ENDPOINT) or _DEFAULT_ENDPOINT
    search_engine_id = getattr(tool_config, "search_engine_id", None)
    if not search_engine_id:
        search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

    timeout_seconds = _coerce_timeout(tool_config.timeout)
    client_timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    base_params: dict[str, Any] = {"key": api_key}
    if search_engine_id:
        base_params["cx"] = search_engine_id
    else:
        logger.debug("No search engine identifier configured for Google Search API")

    results: list[GoogleSearchResult] = []
    seen_links: set[str] = set()
    start_index = 1

    async with aiohttp.ClientSession(timeout=client_timeout) as session:
        while len(results) < validated.max_results:
            page_size = min(_MAX_PAGE_SIZE, validated.max_results - len(results))
            if page_size <= 0:
                break

            params = {
                **base_params,
                "q": validated.query,
                "num": page_size,
                "start": start_index,
            }
            log_params = {k: v for k, v in params.items() if k != "key"}
            logger.debug("Requesting Google Search API with params %s", log_params)

            try:
                payload = await _perform_request(session, endpoint, params)
            except GoogleSearchError as exc:
                message = str(exc)
                if not search_engine_id and "cx" in message.lower():
                    msg = (
                        "Google Search API requires a Programmable Search Engine identifier. "
                        "Set the GOOGLE_SEARCH_ENGINE_ID environment variable or configure "
                        "`search_engine_id` in the search_google tool settings."
                    )
                    raise GoogleSearchError(msg) from exc
                raise

            items = payload.get("items")
            if not isinstance(items, list) or not items:
                logger.debug("No results returned for query '%s'", validated.query)
                break

            for item in items:
                if len(results) >= validated.max_results:
                    break
                if not isinstance(item, dict):
                    continue

                link = _normalize_text(item.get("link"))
                if not link or not link.startswith("http") or link in seen_links:
                    continue

                title = _normalize_text(item.get("title")) or link
                snippet = _normalize_snippet(item)

                results.append(
                    GoogleSearchResult(
                        title=title,
                        link=link,
                        snippet=snippet,
                    ),
                )
                seen_links.add(link)

            next_index = _next_start_index(payload)
            if not next_index or next_index <= start_index:
                break

            start_index = next_index

    return GoogleSearchResults(results=results)
