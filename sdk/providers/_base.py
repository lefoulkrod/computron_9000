"""Base class for API-key-based LLM providers (OpenAI, Anthropic, etc.)."""

from collections.abc import AsyncGenerator, Callable
from typing import Any

from config import LLMConfig

from ._models import ChatDelta, ChatResponse, ProviderError


class BaseAPIProvider:
    """Shared base for providers that authenticate via API key.

    Subclass this for providers like OpenAI or Anthropic. Override
    ``chat()`` and ``list_models()`` when implementing the provider.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url

    @classmethod
    def from_config(cls, llm_config: LLMConfig) -> "BaseAPIProvider":
        """Construct from application config."""
        return cls(api_key=llm_config.api_key, base_url=llm_config.base_url)

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool = False,
    ) -> ChatResponse:
        raise NotImplementedError(f"{type(self).__name__} is not yet implemented")

    async def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool = False,
    ) -> AsyncGenerator[ChatDelta | ChatResponse, None]:
        """Default fallback: call chat() and yield the complete response."""
        yield await self.chat(
            model=model, messages=messages, tools=tools, options=options, think=think,
        )

    async def list_models(self) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__} is not yet implemented")

    async def list_models_detailed(self) -> list[dict[str, Any]]:
        """Return models with metadata. Default wraps list_models() for cloud providers."""
        try:
            names = await self.list_models()
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(str(exc), retryable=False, cause=exc) from exc
        return [
            {
                "name": name,
                "parameter_size": None,
                "quantization_level": None,
                "family": None,
                "capabilities": [],
                "is_cloud": True,
            }
            for name in names
        ]

    def invalidate_model_cache(self) -> None:
        """Clear the model cache. Subclasses that cache should override this."""
