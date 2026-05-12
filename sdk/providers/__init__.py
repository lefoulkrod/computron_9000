"""Provider registry and factory for LLM providers."""

import importlib
import logging
from pathlib import Path
from typing import Any

from config import LLMConfig, load_config
from settings import load_settings

from ._models import ChatDelta, ChatMessage, ChatResponse, ModelInfo, ProviderError, TokenUsage, ToolCall, ToolCallFunction
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


def _resolve_ollama_base_url() -> str:
    """Determine the Ollama base URL from settings or config fallbacks."""
    settings = load_settings()
    if settings.get("llm_provider") == "ollama" and settings.get("llm_base_url"):
        return settings["llm_base_url"]
    cfg = load_config()
    return cfg.llm.host or "http://host.docker.internal:11434"


def _create_provider(provider_name: str) -> Provider:
    """Instantiate a provider by name."""
    path = _PROVIDER_PATHS.get(provider_name)
    if path is None:
        msg = f"Unknown LLM provider: {provider_name!r}. Available: {sorted(_PROVIDER_PATHS)}"
        raise ValueError(msg)

    module_path, cls_name = path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, cls_name)

    if provider_name == "ollama":
        base_url = _resolve_ollama_base_url()
        llm_cfg = LLMConfig(provider="ollama", base_url=base_url)
        instance = cls.from_config(llm_cfg)
        logger.info("Initialized LLM provider: ollama (direct, %s)", base_url)
    else:
        # Cloud providers with a base_url in settings connect directly;
        # otherwise route through the broker proxy socket.
        settings = load_settings()
        if settings.get("llm_provider") == provider_name and settings.get("llm_base_url"):
            llm_cfg = LLMConfig(provider=provider_name, base_url=settings["llm_base_url"])
            instance = cls.from_config(llm_cfg)
            logger.info("Initialized LLM provider: %s (direct)", provider_name)
        else:
            proxy_socket = _proxy_socket_path(provider_name)
            if not proxy_socket.exists():
                msg = (
                    f"Provider {provider_name!r} is not configured — "
                    f"add it via Settings > Integrations"
                )
                raise ValueError(msg)
            instance = cls(proxy_socket=proxy_socket)
            logger.info(
                "Initialized LLM provider: %s (via broker at %s)",
                provider_name, proxy_socket,
            )
    return instance


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


def get_default_provider() -> Provider:
    """Return the provider configured as the system-wide default."""
    settings = load_settings()
    return get_provider(settings.get("llm_provider", "ollama"))


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
    "get_default_provider",
    "get_provider",
    "llm_runtime_stats",
    "reset_provider",
    "vision_generate",
]
