"""Provider protocol defining the interface all LLM providers must implement."""

from collections.abc import AsyncGenerator, Callable
from typing import Any, Protocol

from config import LLMConfig

from ._models import ChatDelta, ChatResponse, ModelInfo


class Provider(Protocol):
    """Interface that every LLM provider must satisfy."""

    @classmethod
    def from_config(cls, llm_config: LLMConfig) -> "Provider":
        """Construct a provider instance from application config."""
        ...

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool = False,
    ) -> ChatResponse:
        """Send a chat completion request and return a normalized response."""
        ...

    def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool = False,
    ) -> AsyncGenerator[ChatDelta | ChatResponse, None]:
        """Stream token deltas followed by a final ChatResponse."""
        ...

    async def list_models(self) -> list[ModelInfo]:
        """Return available models with metadata."""
        ...

    def invalidate_model_cache(self) -> None:
        """Clear cached model metadata."""
        ...
