"""Provider registry and factory for LLM providers."""

import importlib
import logging
from pathlib import Path

from config import load_config
from settings import load_settings

from ._models import ChatDelta, ChatMessage, ChatResponse, LLMConfig, ModelInfo, ProviderError, TokenUsage, ToolCall, ToolCallFunction
from ._protocol import Provider
from ._runtime_stats import LLMRuntimeStats, llm_runtime_stats
from ._vision import vision_generate

logger = logging.getLogger(__name__)

_PROVIDER_PATHS: dict[str, str] = {
    "ollama": "sdk.providers._ollama:OllamaProvider",
    "openai": "sdk.providers._openai_responses:OpenAIResponsesProvider",
    "openai_compat": "sdk.providers._openai:OpenAIProvider",
    "openrouter": "sdk.providers._openai:OpenAIProvider",
    "anthropic": "sdk.providers._anthropic:AnthropicProvider",
}

_provider_cache: dict[str, Provider] = {}


def _proxy_socket_path(provider: str) -> Path:
    """Return the broker socket path for the given provider.

    LLM integrations are singletons — no suffix — so the integration ID
    is just ``llm_{provider}`` and the socket is ``llm_{provider}.sock``.
    """
    sockets_dir = Path(load_config().integrations.sockets_dir)
    return sockets_dir / f"llm_{provider}.sock"


def _provider_class(provider_name: str) -> type:
    """Resolve the provider class for a name, raising on unknown names."""
    path = _PROVIDER_PATHS.get(provider_name)
    if path is None:
        msg = f"Unknown LLM provider: {provider_name!r}. Available: {sorted(_PROVIDER_PATHS)}"
        raise ValueError(msg)
    module_path, cls_name = path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, cls_name)


def _create_provider(provider_name: str) -> Provider:
    """Instantiate a provider by name.

    Direct providers (Ollama, no-auth OpenAI-compatible) are configured in
    ``settings.direct_providers`` and connect straight to their base URL.
    Everything else is a brokered integration reached through a Unix socket.
    A name with neither is not configured.
    """
    cls = _provider_class(provider_name)

    direct = load_settings().get("direct_providers", {}).get(provider_name)
    if direct and direct.get("base_url"):
        instance = cls.from_config(LLMConfig(provider=provider_name, base_url=direct["base_url"]))
        logger.info("Initialized LLM provider: %s (direct, %s)", provider_name, direct["base_url"])
        return instance

    proxy_socket = _proxy_socket_path(provider_name)
    if proxy_socket.exists():
        instance = cls(proxy_socket=proxy_socket)
        logger.info("Initialized LLM provider: %s (via broker at %s)", provider_name, proxy_socket)
        return instance

    msg = f"Provider {provider_name!r} is not configured — add it on the Providers page"
    raise ValueError(msg)


def get_provider(provider_name: str) -> Provider:
    """Return a cached provider instance for the given provider name.

    Each provider name gets at most one cached instance. The instance is
    created on first access and reused until ``reset_provider()`` clears it.
    """
    cached = _provider_cache.get(provider_name)
    if cached is not None:
        return cached
    instance = _create_provider(provider_name)
    _provider_cache[provider_name] = instance
    return instance


def reset_provider(provider_name: str | None = None) -> None:
    """Clear cached provider(s) so the next call re-creates them.

    Args:
        provider_name: Clear a specific provider, or all if None.
    """
    if provider_name is None:
        _provider_cache.clear()
    else:
        _provider_cache.pop(provider_name, None)


__all__ = [
    "ChatDelta",
    "ChatMessage",
    "ChatResponse",
    "LLMRuntimeStats",
    "ModelInfo",
    "Provider",
    "ProviderError",
    "TokenUsage",
    "ToolCall",
    "ToolCallFunction",
    "get_provider",
    "llm_runtime_stats",
    "reset_provider",
    "vision_generate",
]
