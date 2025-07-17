import logging

from ollama import ChatResponse, GenerateResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMRuntimeStats(BaseModel):
    """Pydantic model for LLM runtime statistics.

    Attributes:
        total_duration (Optional[float]): Total duration in seconds.
        load_duration (Optional[float]): Model load duration in seconds.
        prompt_eval_count (Optional[int]): Number of prompt tokens evaluated.
        prompt_eval_duration (Optional[float]): Prompt evaluation duration in seconds.
        prompt_tokens_per_sec (Optional[float]): Prompt tokens per second.
        eval_count (Optional[int]): Number of eval tokens.
        eval_duration (Optional[float]): Eval duration in seconds.
        eval_tokens_per_sec (Optional[float]): Eval tokens per second.

    """

    total_duration: float | None = None
    load_duration: float | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration: float | None = None
    prompt_tokens_per_sec: float | None = None
    eval_count: int | None = None
    eval_duration: float | None = None
    eval_tokens_per_sec: float | None = None


def llm_runtime_stats(response: ChatResponse | GenerateResponse) -> LLMRuntimeStats:
    """Extracts and converts LLM runtime statistics from the response object.

    Args:
        response (ChatResponse | GenerateResponse): The LLM response object with runtime attributes.

    Returns:
        LLMRuntimeStats: Parsed and converted runtime statistics.

    """

    def ns_to_s(ns: int | None) -> float | None:
        return ns / 1_000_000_000 if ns is not None else None

    total_duration = ns_to_s(getattr(response, "total_duration", None))
    load_duration = ns_to_s(getattr(response, "load_duration", None))
    prompt_eval_count = getattr(response, "prompt_eval_count", None)
    prompt_eval_duration = ns_to_s(getattr(response, "prompt_eval_duration", None))
    eval_count = getattr(response, "eval_count", None)
    eval_duration = ns_to_s(getattr(response, "eval_duration", None))
    prompt_tokens_per_sec = (
        prompt_eval_count / prompt_eval_duration
        if (prompt_eval_count and prompt_eval_duration)
        else None
    )
    eval_tokens_per_sec = eval_count / eval_duration if (eval_count and eval_duration) else None
    return LLMRuntimeStats(
        total_duration=total_duration,
        load_duration=load_duration,
        prompt_eval_count=prompt_eval_count,
        prompt_eval_duration=prompt_eval_duration,
        prompt_tokens_per_sec=prompt_tokens_per_sec,
        eval_count=eval_count,
        eval_duration=eval_duration,
        eval_tokens_per_sec=eval_tokens_per_sec,
    )
