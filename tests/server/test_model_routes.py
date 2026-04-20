"""Tests for server._model_routes HTTP handlers.

Focused on: error sanitization (no raw exception messages leak to responses),
capability filtering, and refresh invalidation.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sdk.providers._models import ProviderError
from server._model_routes import handle_list_models, handle_refresh_models


def _make_request(query: dict | None = None) -> MagicMock:
    """Build a minimal aiohttp.web.Request-ish double."""
    req = MagicMock()
    req.query = query or {}
    return req


@pytest.fixture(autouse=True)
def _patch_llm_host():
    """Avoid config.yaml dependency in _llm_host()."""
    with patch("server._model_routes.load_config") as mock_cfg:
        mock_cfg.return_value.llm.host = "http://localhost:11434"
        yield


@pytest.mark.unit
class TestHandleListModels:
    async def test_returns_models_list(self):
        """Successful provider response is forwarded as JSON."""
        models = [
            {"name": "gpt-4", "capabilities": ["vision"]},
            {"name": "gpt-3.5", "capabilities": []},
        ]
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models_detailed.return_value = models
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request())

        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["models"] == models

    async def test_provider_error_no_status_code_returns_generic_message(self):
        """ProviderError without status_code must return 'Provider is unreachable'."""
        exc = ProviderError(
            "Connection refused to api.key=sk-secret-abc123",
            retryable=True,
            status_code=None,
        )
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models_detailed.side_effect = exc
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request())

        assert resp.status == 503
        body = json.loads(resp.body)
        assert body["error"] == "provider_unreachable"
        # Must not leak any part of the raw exception string (could contain API keys)
        assert "sk-secret-abc123" not in body["message"]
        assert body["message"] == "Provider is unreachable"

    async def test_provider_error_with_status_code_surfaces_code(self):
        """ProviderError with a status code produces 'HTTP <code>' safe message."""
        exc = ProviderError("Unauthorized sk-key", retryable=False, status_code=401)
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models_detailed.side_effect = exc
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request())

        assert resp.status == 503
        body = json.loads(resp.body)
        assert "sk-key" not in body["message"]
        assert "401" in body["message"]

    async def test_generic_exception_returns_sanitized_message(self):
        """Unexpected exceptions must not leak raw message to the client."""
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models_detailed.side_effect = RuntimeError(
                "internal error with token=sk-top-secret"
            )
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request())

        assert resp.status == 503
        body = json.loads(resp.body)
        assert "sk-top-secret" not in body["message"]
        assert body["message"] == "Provider is unreachable"

    async def test_capability_filter_vision(self):
        """?capability=vision returns only models with that capability."""
        models = [
            {"name": "vision-model", "capabilities": ["vision"]},
            {"name": "text-only", "capabilities": []},
            {"name": "multi", "capabilities": ["vision", "code"]},
        ]
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models_detailed.return_value = models
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request(query={"capability": "vision"}))

        body = json.loads(resp.body)
        names = [m["name"] for m in body["models"]]
        assert "vision-model" in names
        assert "multi" in names
        assert "text-only" not in names

    async def test_capability_filter_empty_result(self):
        """Filter returns empty list when no models match."""
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models_detailed.return_value = [
                {"name": "text-model", "capabilities": []}
            ]
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request(query={"capability": "vision"}))

        body = json.loads(resp.body)
        assert body["models"] == []

    async def test_503_includes_llm_host(self):
        """Error response includes llm_host for wizard display."""
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models_detailed.side_effect = ProviderError("nope")
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request())

        body = json.loads(resp.body)
        assert "llm_host" in body
        assert body["llm_host"] == "http://localhost:11434"


@pytest.mark.unit
class TestHandleRefreshModels:
    async def test_calls_invalidate_model_cache(self):
        """POST /api/models/refresh invalidates the provider cache."""
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_get.return_value = mock_provider

            resp = await handle_refresh_models(_make_request())

        mock_provider.invalidate_model_cache.assert_called_once()
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["ok"] is True
