"""Provider registry and factory for LLM providers."""

import importlib
import logging
from pathlib import Path
from typing import Any

from config import LLMConfig, load_config
from settings import load_settings

from ._models import ChatDelta, ChatMessage, ChatResponse, ProviderError, TokenUsage, ToolCall, ToolCallFunction
from ._protocol import Provider
from ._runtime_stats import LLMRuntimeStats, llm_runtime_stats
from ._vision import vision_generate

logger = logging.getLogger(__name__)

_PROVIDER_PATHS: dict[str, str] = {
    "ollama": "sdk.providers._ollama:OllamaProvider",
    "openai": "sdk.providers._openai:OpenAIProvider",
    "openai_compat": "sdk.providers._openai:OpenAIProvider",
    "anthropic": "sdk.providers._anthropic:AnthropicProvider",
}

_cached_provider: Any | None = None


def _get_llm_config(settings: dict[str, Any]) -> LLMConfig:
    """Build LLM config from the given settings dict."""
    return LLMConfig(
        provider=settings.get("llm_provider", "ollama"),
        base_url=settings.get("llm_base_url") or None,
    )


def _proxy_socket_path(provider: str) -> Path:
    """Return the broker socket path for the given provider.

    LLM integrations are singletons — no suffix — so the integration ID
    is just ``llm_{provider}`` and the socket is ``llm_{provider}.sock``.
    """
    sockets_dir = Path(load_config().integrations.sockets_dir)
    return sockets_dir / f"llm_{provider}.sock"


def get_provider() -> Provider:
    """Return the configured LLM provider singleton.

    Reads settings.json to determine the provider and connection mode.
    When ``llm_base_url`` is set the provider connects directly. When it's
    absent the provider routes through the broker at the well-known socket
    path for that provider. The result is cached for the process lifetime
    (or until ``reset_provider()`` is called).
    """
    global _cached_provider  # noqa: PLW0603
    if _cached_provider is not None:
        return _cached_provider

    settings = load_settings()
    llm_cfg = _get_llm_config(settings)
    path = _PROVIDER_PATHS.get(llm_cfg.provider)
    if path is None:
        msg = f"Unknown LLM provider: {llm_cfg.provider!r}. Available: {sorted(_PROVIDER_PATHS)}"
        raise ValueError(msg)

    module_path, cls_name = path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, cls_name)

    if llm_cfg.base_url:
        _cached_provider = cls.from_config(llm_cfg)
        logger.info("Initialized LLM provider: %s (direct)", llm_cfg.provider)
    else:
        proxy_socket = _proxy_socket_path(llm_cfg.provider)
        _cached_provider = cls(proxy_socket=proxy_socket)
        logger.info(
            "Initialized LLM provider: %s (via broker at %s)",
            llm_cfg.provider, proxy_socket,
        )
    return _cached_provider


def reset_provider() -> None:
    """Clear the cached provider singleton so the next call re-reads config."""
    global _cached_provider  # noqa: PLW0603
    _cached_provider = None


__all__ = [
    "ChatDelta",
    "ChatMessage",
    "ChatResponse",
    "LLMRuntimeStats",
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
