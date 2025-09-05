import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, Protocol, cast, get_args, get_origin

from ollama import ChatResponse

from agents.types import Agent

from .tool_loop import run_tool_call_loop

logger = logging.getLogger(__name__)


class AgentToolConversionError(Exception):
    """Raised when converting an agent tool result to the requested type fails.

    The concrete error message is determined by ``kind`` to keep raise sites concise
    and consistent with linting guidance.
    """

    ERR_NOT_JSON = "not_json"
    ERR_PYDANTIC_VALIDATE = "pydantic_validate"
    ERR_PYDANTIC_PARSE = "pydantic_parse"
    ERR_CAST = "cast"

    def __init__(self, kind: str) -> None:
        """Initialize the conversion error with a standardized message.

        Args:
            kind (str): Predefined error kind determining the message.
        """
        messages = {
            self.ERR_NOT_JSON: "Result was not valid JSON for requested non-string type",
            self.ERR_PYDANTIC_VALIDATE: "Failed to validate JSON into Pydantic model",
            self.ERR_PYDANTIC_PARSE: "Failed to parse JSON into Pydantic model",
            self.ERR_CAST: "Failed to cast JSON to requested type",
        }
        super().__init__(messages.get(kind, "Agent tool conversion error"))
        self.kind = kind


class _PydanticV2(Protocol):
    def model_validate(self, obj: object, /) -> object:  # pragma: no cover - protocol
        ...


class _PydanticV1(Protocol):
    def parse_obj(self, obj: object, /) -> object:  # pragma: no cover - protocol
        ...


def _validate_pydantic_model(
    model_type: _PydanticV2 | _PydanticV1 | type,
    data: object,
    *,
    context: str,
) -> object:
    """Validate ``data`` against a Pydantic model type (v2 preferred, v1 compatible).

    Args:
        model_type (Any): Pydantic model class (v2 or v1 style).
        data (Any): Parsed JSON to validate/parse.
        context (str): Extra context for error logs (e.g., "for list element type").

    Returns:
        Any: The validated/parsed model instance.

    Raises:
        AgentToolConversionError: If validation/parsing fails.
    """
    if hasattr(model_type, "model_validate"):
        try:
            return model_type.model_validate(data)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.exception("Pydantic model_validate failed %s %s", context, model_type)
            raise AgentToolConversionError(AgentToolConversionError.ERR_PYDANTIC_VALIDATE) from exc

    if hasattr(model_type, "parse_obj"):
        try:
            return model_type.parse_obj(data)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.exception("Pydantic parse_obj failed %s %s", context, model_type)
            raise AgentToolConversionError(AgentToolConversionError.ERR_PYDANTIC_PARSE) from exc

    return data


def _convert_result_to_type[T](raw_text: str, result_type: type[T]) -> T:
    """Convert accumulated assistant text to a requested type using JSON/Pydantic.

    This expects the assistant's final result to be JSON if ``result_type`` is not ``str``.
    For Pydantic models (v2 preferred, v1 compatible), JSON is parsed into an object via
    ``model_validate``/``parse_obj``. For builtins like ``dict``, ``list``, ``int``, ``float``,
    and ``bool``, ``json.loads`` is used and then cast to the requested type.

    Args:
        raw_text (str): The raw accumulated assistant text.
        result_type (type[T]): The target python type to convert into. Defaults to ``str``
            at the factory call site.

    Returns:
        T: The converted result instance.

    Raises:
        AgentToolConversionError: If conversion fails due to invalid JSON or type mismatch.

    """
    # String fast path is handled by the caller to keep this function focused
    # on JSON-based conversions.

    # Attempt to parse JSON with simple retry for transient formatting issues
    max_attempts = 5
    parsed: Any | None = None
    for attempt in range(max_attempts):
        try:
            parsed = json.loads(raw_text)
            break
        except json.JSONDecodeError as exc:
            if attempt < max_attempts - 1:
                logger.warning(
                    "JSON parse failed attempt %s/%s for type %s",
                    attempt + 1,
                    max_attempts,
                    result_type,
                )
                continue
            logger.exception("Failed to parse agent result as JSON for type %s", result_type)
            raise AgentToolConversionError(AgentToolConversionError.ERR_NOT_JSON) from exc

    # Safety check; parsed must be set when loop breaks
    if parsed is None:  # pragma: no cover - defensive
        logger.error("JSON parse failed without exception for type %s", result_type)
        raise AgentToolConversionError(AgentToolConversionError.ERR_NOT_JSON)

    # Handle list[Model] (PEP 585 GenericAlias) or typing.List[Model]
    origin = get_origin(result_type)
    if origin in (list,):
        # Determine the element type, if any
        args = get_args(result_type)
        elem_type = args[0] if args else None

        if not isinstance(parsed, list):
            logger.exception(
                "Expected JSON array for result_type %s but got %s",
                result_type,
                type(parsed),
            )
            raise AgentToolConversionError(AgentToolConversionError.ERR_CAST)

        # If element type is a Pydantic model, validate each item
        if elem_type is not None and (
            hasattr(elem_type, "model_validate") or hasattr(elem_type, "parse_obj")
        ):
            return cast(
                "T",
                [
                    _validate_pydantic_model(elem_type, item, context="for list element type")
                    for item in parsed
                ],
            )

        # For non-Pydantic element types, return parsed list as-is
        return cast("T", parsed)

    # Pydantic model (v2 or v1)
    if hasattr(result_type, "model_validate") or hasattr(result_type, "parse_obj"):
        return cast("T", _validate_pydantic_model(result_type, parsed, context="for type"))

    # Builtins and general types: return parsed JSON as-is (best-effort)
    # Note: we only guarantee JSON-convertible types; deep type checks are not enforced.
    return cast("T", parsed)


def make_run_agent_as_tool_function[T](
    agent: Agent,
    tool_description: str,
    *,
    result_type: type[T] = str,  # Default behavior returns string
    before_model_callbacks: list[Callable[[list[dict[str, str]]], None]] | None = None,
    after_model_callbacks: list[Callable[[ChatResponse], None]] | None = None,
) -> Callable[[str], Awaitable[T]]:
    """Return an async function that runs the given agent as a tool and returns type ``T``.

    The provided description becomes the tool function's docstring.


    Args:
        agent (Agent): The agent to be run as a tool.
        tool_description (str): The docstring to assign to the returned function.
        result_type (type[T]): The desired return type of the tool function. Defaults to ``str``.
        before_model_callbacks (list[Callable[[list[dict[str, str]]], None]] | None):
            List of callbacks before model call.
        after_model_callbacks (list[Callable[[ChatResponse], None]] | None):
            List of callbacks after model call.

    Returns:
        Callable[[str], Awaitable[T]]: An async function that takes a string
            argument 'instructions' and returns the specified type ``T``.

    """
    docstring = f"""
{tool_description}

Args:
    instructions (str): The detailed instructions for the agent to follow. Including step by step plans if necessary.

Returns:
    {getattr(result_type, "__name__", str(result_type))}: The result returned by the agent after processing the instructions.
"""  # noqa: E501

    async def run_agent_as_tool(instructions: str) -> T:
        # DONT PROVIDE A DOCSTRING HERE
        messages = [
            {"role": "system", "content": agent.instruction},
            {"role": "user", "content": instructions},
        ]
        result_text = ""
        try:
            gen: AsyncGenerator[tuple[str | None, str | None], None] = run_tool_call_loop(
                messages=messages,
                tools=agent.tools,
                model=agent.model,
                model_options=agent.options,
                think=agent.think,
                before_model_callbacks=before_model_callbacks,
                after_model_callbacks=after_model_callbacks,
            )
            # Only keep the last emission's content rather than accumulating all chunks
            async for content, _ in gen:
                if content:
                    result_text = content
        except Exception:
            # Log full traceback and re-raise to avoid swallowing unexpected errors
            logger.exception("Unexpected error running agent tool loop for agent '%s'", agent.name)
            raise
        final_text = result_text.strip()
        # Convert to requested type if needed
        if result_type is str:  # type: ignore[comparison-overlap]
            return final_text  # type: ignore[return-value]
        return _convert_result_to_type(final_text, result_type)

    # Give the tool function a deterministic, agent-derived name so the LLM can
    # distinguish multiple agent tools. We assume agent.name values are unique.
    safe_agent_name = (
        "".join(ch.lower() if ch.isalnum() else "_" for ch in agent.name).strip("_") or "agent"
    )
    func_name = f"run_{safe_agent_name}_as_tool"
    run_agent_as_tool.__name__ = func_name  # type: ignore[attr-defined]
    run_agent_as_tool.__qualname__ = func_name  # type: ignore[attr-defined]
    run_agent_as_tool.__doc__ = docstring
    return run_agent_as_tool
