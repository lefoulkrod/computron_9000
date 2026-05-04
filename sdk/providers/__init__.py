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

logger = logging.getLogger(__name__)

_PROVIDER_PATHS: dict[str, str] = {
    "ollama": "sdk.providers._ollama:OllamaProvider",
    "openai": "sdk.providers._openai:OpenAIProvider",
    "anthropic": "sdk.providers._anthropic:AnthropicProvider",
}

_cached_provider: Any | None = None


def _get_llm_config() -> LLMConfig:
    """Return LLM config merged from config.yaml defaults and settings.json overrides.

    Load order: env var (resolved by load_config) → settings.json → config.yaml defaults.
    The ``host`` field is Ollama-specific and is never overridden by settings.json.
    API keys for cloud providers are no longer stored in settings — they live
    in the supervisor vault and are accessed via the llm_proxy broker.
    """
    base = load_config().llm
    s = load_settings()
    overrides: dict[str, Any] = {}
    if s.get("llm_provider"):
        overrides["provider"] = s["llm_provider"]
    if s.get("llm_base_url"):
        overrides["base_url"] = s["llm_base_url"]
    if not overrides:
        return base
    return base.model_copy(update=overrides)


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

    Reads the merged LLM config (config.yaml + settings.json overrides) to
    determine which provider to instantiate. For cloud providers (openai,
    anthropic) it first checks for a running llm_proxy broker and, if found,
    constructs the SDK client with a UDS transport so the broker handles auth.
    Falls back to a direct connection (``from_config``) for local providers or
    when no proxy socket is present. The result is cached for the process
    lifetime (or until ``reset_provider()`` is called).
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
]
