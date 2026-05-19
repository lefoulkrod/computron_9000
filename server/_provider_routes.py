"""HTTP route handlers for the providers API.

Three handlers:

- ``GET /api/providers`` — list configured providers (direct + brokered).
- ``POST /api/providers`` — add/configure a provider. For direct kinds
  (Ollama, no-auth OpenAI-compatible) writes to ``settings.direct_providers``;
  for brokered kinds creates an ``llm_<name>`` vault integration via the
  supervisor. Probes the new provider and returns its model list (503 on
  unreachable).
- ``DELETE /api/providers/{name}`` — remove. Drops the settings entry for
  a direct provider or asks the supervisor to remove the integration for
  a brokered one.
"""

from __future__ import annotations

import json
import logging
import re

from aiohttp import web
from pydantic import BaseModel, ConfigDict, ValidationError

from integrations.supervisor_client import SupervisorError
from sdk.providers import get_provider, reset_provider
from sdk.providers._models import ProviderError
from server._integrations_routes import _supervisor_call
from settings import _validate_base_url, load_settings, save_settings
from tools.integrations import registered_integrations
from tools.integrations._state import refresh_registered_integrations

logger = logging.getLogger(__name__)

# Provider catalog. The five names the rest of the app recognizes; anything
# else gets rejected at add time.
_KNOWN_PROVIDERS: set[str] = {
    "ollama",
    "openai",
    "anthropic",
    "openrouter",
    "openai_compat",
}

# Provider name → display label. Used for the integration's ``label`` field
# on brokered creates and for surfacing the provider in the UI.
_PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama",
    "openai": "OpenAI API",
    "anthropic": "Anthropic API",
    "openrouter": "OpenRouter",
    "openai_compat": "OpenAI-compatible",
}

# Patterns that could contain credentials — scrubbed before the message
# leaves the process. Same shape as the model routes' sanitizer.
_KEY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-[A-Za-z0-9_-]{10,}"), "sk-***"),
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "Bearer ***"),
]


def _sanitize(msg: str) -> str:
    for pattern, replacement in _KEY_PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg


def _label(name: str) -> str:
    return _PROVIDER_LABELS.get(name, name)


# ── GET ──────────────────────────────────────────────────────────────────


async def handle_list_providers(_request: web.Request) -> web.Response:
    """Return configured LLM providers.

    Direct-connect providers (Ollama, no-auth OpenAI-compatible) come from
    ``settings.direct_providers``; brokered providers come from the
    integrations supervisor (singleton ``llm_<name>`` integrations).

    The supervisor is the source of truth for brokered integrations; the
    app-side cache can lag a mutation done through this same module, so
    refresh it before reading. One extra RPC per Providers-page load.
    """
    settings = load_settings()

    providers: list[dict[str, object]] = []

    for name, entry in (settings.get("direct_providers") or {}).items():
        providers.append({
            "name": name,
            "label": _label(name),
            "kind": "direct",
            "base_url": entry.get("base_url"),
            "status": "configured",
        })

    await refresh_registered_integrations()
    integrations = await registered_integrations()
    for ri in integrations.values():
        if not ri.slug.startswith("llm_"):
            continue
        name = ri.slug.removeprefix("llm_")
        providers.append({
            "name": name,
            "label": _label(name),
            "kind": "brokered",
            "status": ri.state,
        })

    return web.json_response({"providers": providers})


# ── POST ─────────────────────────────────────────────────────────────────


class _AddProviderBody(BaseModel):
    """Schema for ``POST /api/providers``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    base_url: str | None = None
    api_key: str | None = None


async def handle_add_provider(request: web.Request) -> web.Response:
    """Configure a provider, probe it, return its model list.

    Storage choice is implicit: ``api_key`` present → brokered (vault
    integration); absent → direct (``settings.direct_providers`` entry).
    The probe is a single ``list_models()`` call against the just-created
    provider — if it fails the configuration still persists, the caller
    just sees the 503 and can fix the URL/key.
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "Request body must be a JSON object"}, status=400)
    try:
        spec = _AddProviderBody(**body)
    except ValidationError as exc:
        logger.warning("invalid /api/providers body: %s", exc)
        return web.json_response({"error": "Unknown or invalid field"}, status=400)

    name = spec.name
    if name not in _KNOWN_PROVIDERS:
        return web.json_response(
            {"error": f"Unknown provider: {name!r}. "
                     f"Choose one of: {sorted(_KNOWN_PROVIDERS)}"},
            status=400,
        )

    if spec.api_key:
        # Brokered: create the llm_<name> integration in the vault.
        auth_blob: dict[str, str] = {"api_key": spec.api_key}
        if spec.base_url:
            # OpenAI-compat with a key needs the upstream URL stored alongside
            # the key so the broker knows where to forward.
            auth_blob["base_url"] = spec.base_url
        try:
            await _supervisor_call("add", {
                "slug": f"llm_{name}",
                "label": _label(name),
                "auth_blob": auth_blob,
                "permissions": {},
                "write_allowed": False,
            })
        except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
            logger.warning("supervisor unreachable for provider add: %s", exc)
            return web.json_response(
                {"error": "Integrations service isn't running."},
                status=503,
            )
        except SupervisorError as exc:
            return web.json_response({"error": _sanitize(exc.message)}, status=400)
    else:
        # Direct: write the settings.direct_providers entry.
        if not spec.base_url:
            return web.json_response(
                {"error": "base_url is required when no api_key is provided"},
                status=400,
            )
        try:
            _validate_base_url(spec.base_url)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        settings = load_settings()
        direct = dict(settings.get("direct_providers") or {})
        direct[name] = {"base_url": spec.base_url}
        save_settings({"direct_providers": direct})

    # Force the next get_provider(name) to re-build, then probe.
    reset_provider(name)
    try:
        models = await get_provider(name).list_models()
    except ProviderError as exc:
        return web.json_response(
            {
                "error": "provider_unreachable",
                "message": _sanitize(str(exc)),
                "provider": name,
            },
            status=503,
        )
    except Exception as exc:  # noqa: BLE001 - any failure here is "couldn't reach"
        return web.json_response(
            {
                "error": "provider_unreachable",
                "message": _sanitize(str(exc)),
                "provider": name,
            },
            status=503,
        )

    return web.json_response(
        {
            "provider": {
                "name": name,
                "label": _label(name),
                "kind": "brokered" if spec.api_key else "direct",
                "base_url": spec.base_url if not spec.api_key else None,
                "status": "connected",
            },
            "models": [m.model_dump() for m in models],
        },
        status=201,
    )


# ── DELETE ───────────────────────────────────────────────────────────────


async def handle_remove_provider(request: web.Request) -> web.Response:
    """Remove a provider.

    For a direct provider the settings entry is dropped; for a brokered
    one the supervisor's ``remove`` RPC tears down the broker process and
    deletes the vault entry. Returns 404 if the name doesn't match any
    configured provider.
    """
    name = request.match_info["name"]
    if name not in _KNOWN_PROVIDERS:
        return web.json_response({"error": f"Unknown provider: {name!r}"}, status=400)

    settings = load_settings()
    direct = dict(settings.get("direct_providers") or {})
    if name in direct:
        del direct[name]
        save_settings({"direct_providers": direct})
        reset_provider(name)
        return web.json_response({"ok": True})

    integrations = await registered_integrations()
    target_slug = f"llm_{name}"
    for ri in integrations.values():
        if ri.slug == target_slug:
            try:
                await _supervisor_call("remove", {"id": ri.id})
            except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
                logger.warning("supervisor unreachable for provider remove: %s", exc)
                return web.json_response(
                    {"error": "Integrations service isn't running."},
                    status=503,
                )
            except SupervisorError as exc:
                return web.json_response({"error": _sanitize(exc.message)}, status=400)
            reset_provider(name)
            return web.json_response({"ok": True})

    return web.json_response({"error": f"Provider {name!r} is not configured"}, status=404)


# ── PATCH ────────────────────────────────────────────────────────────────


class _UpdateProviderBody(BaseModel):
    """Schema for ``PATCH /api/providers/{name}``."""

    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    api_key: str | None = None


async def handle_update_provider(request: web.Request) -> web.Response:
    """Update an existing provider's connection details.

    For a direct provider, rewrites its ``settings.direct_providers``
    entry (and validates the new URL). For a brokered one, the supervisor
    has no auth_blob-aware update verb yet, so the change is implemented
    as remove + add server-side — keeping the operation atomic from the
    client's perspective. Either way the cache is dropped and a probe is
    run; the response shape matches ``POST /api/providers``.
    """
    name = request.match_info["name"]
    if name not in _KNOWN_PROVIDERS:
        return web.json_response({"error": f"Unknown provider: {name!r}"}, status=400)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "Request body must be a JSON object"}, status=400)
    try:
        spec = _UpdateProviderBody(**body)
    except ValidationError as exc:
        logger.warning("invalid PATCH /api/providers body: %s", exc)
        return web.json_response({"error": "Unknown or invalid field"}, status=400)

    settings = load_settings()
    direct = dict(settings.get("direct_providers") or {})

    if name in direct:
        # Direct kind — update the base_url.
        if not spec.base_url:
            return web.json_response(
                {"error": "base_url is required to update a direct provider"},
                status=400,
            )
        try:
            _validate_base_url(spec.base_url)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        direct[name] = {"base_url": spec.base_url}
        save_settings({"direct_providers": direct})
        kind = "direct"
        stored_base_url: str | None = spec.base_url
    else:
        # Brokered kind — must currently exist as an llm_<name> integration.
        integrations = await registered_integrations()
        target_slug = f"llm_{name}"
        existing = next((ri for ri in integrations.values() if ri.slug == target_slug), None)
        if existing is None:
            return web.json_response(
                {"error": f"Provider {name!r} is not configured"},
                status=404,
            )
        if not spec.api_key:
            return web.json_response(
                {"error": "api_key is required to update a brokered provider"},
                status=400,
            )
        auth_blob: dict[str, str] = {"api_key": spec.api_key}
        if spec.base_url:
            auth_blob["base_url"] = spec.base_url
        # Atomic-ish: remove, then add with the new auth_blob. The supervisor
        # doesn't currently expose an auth_blob-aware update verb; revisit
        # when it does.
        try:
            await _supervisor_call("remove", {"id": existing.id})
            await _supervisor_call("add", {
                "slug": target_slug,
                "label": _label(name),
                "auth_blob": auth_blob,
                "permissions": {},
                "write_allowed": False,
            })
        except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
            logger.warning("supervisor unreachable for provider update: %s", exc)
            return web.json_response(
                {"error": "Integrations service isn't running."},
                status=503,
            )
        except SupervisorError as exc:
            return web.json_response({"error": _sanitize(exc.message)}, status=400)
        kind = "brokered"
        stored_base_url = None

    reset_provider(name)
    try:
        models = await get_provider(name).list_models()
    except Exception as exc:  # noqa: BLE001 - any failure here is "couldn't reach"
        return web.json_response(
            {
                "error": "provider_unreachable",
                "message": _sanitize(str(exc)),
                "provider": name,
            },
            status=503,
        )

    return web.json_response({
        "provider": {
            "name": name,
            "label": _label(name),
            "kind": kind,
            "base_url": stored_base_url,
            "status": "connected",
        },
        "models": [m.model_dump() for m in models],
    })


def register_provider_routes(app: web.Application) -> None:
    """Register provider API routes."""
    app.router.add_route("GET", "/api/providers", handle_list_providers)
    app.router.add_route("POST", "/api/providers", handle_add_provider)
    app.router.add_route("PATCH", "/api/providers/{name}", handle_update_provider)
    app.router.add_route("DELETE", "/api/providers/{name}", handle_remove_provider)
