"""Provider registry and factory for LLM providers."""

import importlib
import logging
from typing import Any

from config import load_config

from ._models import ChatMessage, ChatResponse, ProviderError, TokenUsage, ToolCall, ToolCallFunction
from ._protocol import Provider
from ._runtime_stats import LLMRuntimeStats, llm_runtime_stats

logger = logging.getLogger(__name__)

_PROVIDER_PATHS: dict[str, str] = {
    "ollama": "sdk.providers._ollama:OllamaProvider",
    "openai": "sdk.providers._openai:OpenAIProvider",
    "anthropic": "sdk.providers._anthropic:AnthropicProvider",
}

_cached_provider: Any | None = None


def get_provider() -> Provider:
    """Return the configured LLM provider singleton.

    Reads ``cfg.llm.provider`` to determine which provider to instantiate,
    looks up the dotted path in the registry, and calls ``cls.from_config()``.
    The result is cached for the lifetime of the process.
    """
    global _cached_provider  # noqa: PLW0603
    if _cached_provider is not None:
        return _cached_provider

    cfg = load_config()
    provider_name = cfg.llm.provider
    path = _PROVIDER_PATHS.get(provider_name)
    if path is None:
        msg = f"Unknown LLM provider: {provider_name!r}. Available: {sorted(_PROVIDER_PATHS)}"
        raise ValueError(msg)

    module_path, cls_name = path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, cls_name)

    _cached_provider = cls.from_config(cfg.llm)
    logger.info("Initialized LLM provider: %s", provider_name)
    return _cached_provider


def reset_provider() -> None:
    """Clear the cached provider singleton. Intended for testing."""
    global _cached_provider  # noqa: PLW0603
    _cached_provider = None


__all__ = [
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
