"""Normalized response types for provider-agnostic LLM interactions.

Each provider normalizes its native response into these types so consumer
code never touches provider-specific objects.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMConfig(BaseModel):
    """Connection parameters for constructing a direct-connect LLM provider.

    Direct providers carry no credentials (Ollama and no-auth OpenAI-compat
    endpoints) — just the base URL to connect to.
    """

    provider: str = "ollama"
    base_url: str | None = None


class ProviderError(Exception):
    """Error raised by an LLM provider with retryability information.

    Attributes:
        retryable: Whether the caller should retry the request.
        status_code: HTTP status code if applicable.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        if cause is not None:
            self.__cause__ = cause


class ToolCallFunction(BaseModel):
    """Normalized function within a tool call."""

    name: str
    arguments: dict[str, Any]


class ToolCall(BaseModel):
    """A single tool invocation requested by the model."""

    id: str | None = None
    function: ToolCallFunction


class ChatMessage(BaseModel):
    """Provider-agnostic assistant message from a chat completion."""

    content: str | None = None
    thinking: str | None = None
    tool_calls: list[ToolCall] | None = None


class TokenUsage(BaseModel):
    """Normalized token counts."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


class ChatDelta(BaseModel):
    """A single incremental token fragment from a streaming chat response."""

    content: str | None = None
    thinking: str | None = None


class ChatResponse(BaseModel):
    """Normalized response from any provider's chat endpoint."""

    message: ChatMessage
    usage: TokenUsage = Field(default_factory=TokenUsage)
    done_reason: str | None = None
    raw: Any = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ModelInfo(BaseModel):
    """Metadata for an available model, returned by provider.list_models()."""

    name: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_images: bool = False
    supports_thinking: bool = False
    parameter_size: str | None = None
    quantization_level: str | None = None
    family: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    is_cloud: bool = False
