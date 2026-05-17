"""Tests for server._model_routes HTTP handlers.

Focused on: ``?provider=`` being required, error sanitization (no raw
credentials leak to responses), and refresh invalidation.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sdk.providers._models import ModelInfo, ProviderError
from server._model_routes import handle_list_models, handle_refresh_models


def _make_request(query: dict | None = None) -> MagicMock:
    """Build a minimal aiohttp.web.Request-ish double.

    Defaults to ``?provider=ollama`` so the handler resolves a provider
    (which these tests patch). Pass ``{}`` to test the missing-provider path.
    """
    req = MagicMock()
    req.query = query if query is not None else {"provider": "ollama"}
    return req


@pytest.mark.unit
class TestHandleListModels:
    async def test_requires_provider(self):
        """Missing ?provider= → 400."""
        resp = await handle_list_models(_make_request({}))
        assert resp.status == 400

    async def test_unknown_provider_is_400(self):
        """A provider name that can't be resolved → 400, not 503."""
        with patch("server._model_routes.get_provider", side_effect=ValueError("not configured")):
            resp = await handle_list_models(_make_request())
        assert resp.status == 400

    async def test_returns_models_list(self):
        """Successful provider response is forwarded as JSON."""
        models = [
            ModelInfo(name="gpt-4", supports_images=True, capabilities=["vision"]),
            ModelInfo(name="gpt-3.5"),
        ]
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models.return_value = models
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request())

        assert resp.status == 200
        body = json.loads(resp.body)
        assert [m["name"] for m in body["models"]] == ["gpt-4", "gpt-3.5"]

    async def test_provider_error_message_is_sanitized(self):
        """Provider errors pass through with credential-shaped tokens redacted."""
        exc = ProviderError("Connection refused to api.key=sk-secret-abc123", retryable=True)
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models.side_effect = exc
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request())

        assert resp.status == 503
        body = json.loads(resp.body)
        assert body["error"] == "provider_unreachable"
        assert body["provider"] == "ollama"
        assert "sk-secret-abc123" not in body["message"]
        assert "Connection refused" in body["message"]

    async def test_status_code_surfaced_in_message(self):
        """A status-code error keeps the informative text, scrubs the key."""
        exc = ProviderError(
            "Error code: 401 - {'error': {'message': 'Invalid API key'}} sk-abc123456789",
            retryable=False,
            status_code=401,
        )
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models.side_effect = exc
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request())

        body = json.loads(resp.body)
        assert resp.status == 503
        assert "sk-abc123456789" not in body["message"]
        assert "401" in body["message"]
        assert "Invalid API key" in body["message"]

    async def test_generic_exception_message_is_sanitized(self):
        """Unexpected exceptions also pass through a sanitized message."""
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.list_models.side_effect = RuntimeError("internal error with Bearer sk-top-secret")
            mock_get.return_value = mock_provider

            resp = await handle_list_models(_make_request())

        body = json.loads(resp.body)
        assert resp.status == 503
        assert "sk-top-secret" not in body["message"]
        assert "internal error" in body["message"]


@pytest.mark.unit
class TestHandleRefreshModels:
    async def test_requires_provider(self):
        resp = await handle_refresh_models(_make_request({}))
        assert resp.status == 400

    async def test_calls_invalidate_model_cache(self):
        """POST /api/models/refresh invalidates the provider's model cache."""
        with patch("server._model_routes.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_get.return_value = mock_provider

            resp = await handle_refresh_models(_make_request())

        mock_provider.invalidate_model_cache.assert_called_once()
        assert resp.status == 200
        assert json.loads(resp.body)["ok"] is True
