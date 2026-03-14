"""Base class for API-key-based LLM providers (OpenAI, Anthropic, etc.)."""

from collections.abc import Callable
from typing import Any

from config import LLMConfig

from ._models import ChatResponse


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

    async def list_models(self) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__} is not yet implemented")
