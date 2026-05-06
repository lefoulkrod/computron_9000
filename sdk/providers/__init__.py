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
    "anthropic": "sdk.providers._anthropic:AnthropicProvider",
}

_cached_provider: Any | None = None


def _get_llm_config() -> LLMConfig:
    """Return LLM config from settings.json (written by the setup wizard).

    API keys for cloud providers live in the supervisor vault and are accessed
    via the llm_proxy broker — they are never stored in settings.
    """
    s = load_settings()
    return LLMConfig(
        provider=s.get("llm_provider", "ollama"),
        base_url=s.get("llm_base_url") or None,
    )


def _find_proxy_socket(provider: str) -> Path | None:
    """Return the running llm_proxy broker socket path for ``provider``, or None.

    The supervisor spawns the llm_proxy broker as ``llm_proxy_{provider}``
    (e.g. ``llm_proxy_openai``). The socket lives at
    ``{sockets_dir}/llm_proxy_{provider}.sock``. If the file exists the
    broker is running (or was running and left a stale socket — the provider
    will see a connection error on first use, which is retryable).
    """
    sockets_dir = Path(load_config().integrations.sockets_dir)
    sock = sockets_dir / f"llm_proxy_{provider}.sock"
    return sock if sock.exists() else None


def get_provider() -> Provider:
    """Return the configured LLM provider singleton.

    Reads provider settings from settings.json to determine which provider to
    instantiate. For cloud providers (openai, anthropic) it first checks for a
    running llm_proxy broker and, if found, constructs the SDK client with a
    UDS transport so the broker handles auth. Falls back to a direct connection
    for local providers or when no proxy socket is present. The result is cached
    for the process lifetime (or until ``reset_provider()`` is called).
    """
    global _cached_provider  # noqa: PLW0603
    if _cached_provider is not None:
        return _cached_provider

    llm_cfg = _get_llm_config()
    path = _PROVIDER_PATHS.get(llm_cfg.provider)
    if path is None:
        msg = f"Unknown LLM provider: {llm_cfg.provider!r}. Available: {sorted(_PROVIDER_PATHS)}"
        raise ValueError(msg)

    module_path, cls_name = path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, cls_name)

    proxy_socket = _find_proxy_socket(llm_cfg.provider)
    if proxy_socket is not None:
        _cached_provider = cls(proxy_socket=proxy_socket)
        logger.info(
            "Initialized LLM provider: %s (via proxy socket %s)",
            llm_cfg.provider, proxy_socket,
        )
    else:
        _cached_provider = cls.from_config(llm_cfg)
        logger.info("Initialized LLM provider: %s", llm_cfg.provider)
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
