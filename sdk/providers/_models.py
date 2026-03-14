"""Normalized response types for provider-agnostic LLM interactions.

Each provider normalizes its native response into these types so consumer
code never touches provider-specific objects.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class ChatResponse(BaseModel):
    """Normalized response from any provider's chat endpoint."""

    message: ChatMessage
    usage: TokenUsage = Field(default_factory=TokenUsage)
    done_reason: str | None = None
    raw: Any = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
