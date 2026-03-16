"""Helpers to wrap agents as callable tools and convert tool outputs.

Provides utilities to convert assistant text into typed Python values and to
produce async tool-call wrappers from agent instances.
"""

import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, Protocol, cast, get_args, get_origin

from agents.types import Agent
from sdk.context import ContextManager, ConversationHistory, SummarizeStrategy
from sdk.events import agent_span, collect_sub_agent_history, get_model_options
from sdk.hooks import default_hooks
from sdk.loop import StopRequestedError, run_tool_call_loop


class AgentToolMarker:
    """Simple marker mixin to identify agent-backed tool wrappers."""


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
            return model_type.model_validate(data)
        except Exception as exc:
            logger.exception("Pydantic model_validate failed %s %s", context, model_type)
            raise AgentToolConversionError(AgentToolConversionError.ERR_PYDANTIC_VALIDATE) from exc

    if hasattr(model_type, "parse_obj"):
        try:
            return model_type.parse_obj(data)
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

    # Parse JSON once; caller is responsible for retrying the tool loop on failure
    try:
        parsed: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.exception("Failed to parse agent result as JSON for type %s", result_type)
        raise AgentToolConversionError(AgentToolConversionError.ERR_NOT_JSON) from exc

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
        if elem_type is not None and (hasattr(elem_type, "model_validate") or hasattr(elem_type, "parse_obj")):
            return cast(
                "T",
                [_validate_pydantic_model(elem_type, item, context="for list element type") for item in parsed],
            )

        # For non-Pydantic element types, return parsed list as-is
        return cast("T", parsed)

    # Pydantic model (v2 or v1)
    if hasattr(result_type, "model_validate") or hasattr(result_type, "parse_obj"):
        return cast("T", _validate_pydantic_model(result_type, parsed, context="for type"))

    # Builtins and general types: return parsed JSON as-is (best-effort)
    # Note: we only guarantee JSON-convertible types; deep type checks are not enforced.
    return cast("T", parsed)


async def _run_tool_loop_once(
    *,
    history: ConversationHistory,
    agent: Agent,
    hooks: list[Any],
) -> str:
    """Run the tool-call loop once and return the final assistant text.

    Args:
        history: Conversation history to seed the model/tool loop.
        agent: Agent providing tools, model, options, and think flag.
        hooks: Loop hooks for all four phases.

    Returns:
        The last emitted assistant content, stripped.

    Raises:
        Propagates any unexpected exceptions from the tool loop after logging.
    """
    result_text = ""
    try:
        gen: AsyncGenerator[tuple[str | None, str | None], None] = run_tool_call_loop(
            history=history,
            agent=agent,
            hooks=hooks,
        )
        async for content, _ in gen:
            if content:
                result_text = content
    except StopRequestedError:
        logger.info("Agent tool '%s' stopped by user request", agent.name)
        raise
    except Exception:
        logger.exception(
            "Unexpected error running agent tool loop for agent '%s'",
            agent.name,
        )
        raise

    return result_text.strip()


async def _run_with_json_retry[T](
    *,
    history: ConversationHistory,
    agent: Agent,
    result_type: type[T],
    hooks: list[Any],
    max_attempts: int = 5,
) -> T:
    """Run the tool loop with JSON-parse retries for non-string result types.

    Retries the entire tool-call loop up to ``max_attempts`` times when the
    conversion fails specifically due to non-JSON output (ERR_NOT_JSON).

    Args:
        history: Conversation history.
        agent: Agent to execute.
        result_type: The target non-string type to convert the output into.
        hooks: Loop hooks for all four phases.
        max_attempts: Number of attempts to try when JSON parsing fails.

    Returns:
        Parsed/validated result of type ``T``.

    Raises:
        AgentToolConversionError: On final JSON failure or other conversion errors.
        Exception: Any unexpected error raised by the tool loop.
    """
    for attempt in range(max_attempts):
        final_text = await _run_tool_loop_once(
            history=history,
            agent=agent,
            hooks=hooks,
        )
        try:
            return _convert_result_to_type(final_text, result_type)
        except AgentToolConversionError as exc:
            if (
                exc.kind == AgentToolConversionError.ERR_NOT_JSON
                and attempt < max_attempts - 1
            ):
                logger.warning(
                    "Non-JSON tool result, retrying tool loop attempt %s/%s for agent %s",
                    attempt + 1,
                    max_attempts,
                    agent.name,
                )
                continue
            raise
    # Exhausted retries specifically for non-JSON results
    logger.error("Exhausted retries parsing non-string result for agent '%s'", agent.name)
    raise AgentToolConversionError(AgentToolConversionError.ERR_NOT_JSON)


def make_run_agent_as_tool_function[T](
    *,
    name: str,
    description: str,
    instruction: str,
    tools: list[Callable[..., Any]],
    result_type: type[T] = str,  # type: ignore  # Default behavior returns string
    max_iterations: int = 0,
) -> Callable[[str], Awaitable[T]]:
    """Return an async function that runs a freshly constructed agent as a tool.

    The agent is constructed at call time using the static config provided here
    combined with the current request's model options from ``get_model_options()``.

    Args:
        name: Agent name (used for event attribution and function naming).
        description: Becomes the tool's docstring — this is what the calling agent
            sees when deciding whether to use this tool.
        instruction: System prompt for the agent.
        tools: Tool functions available to the agent.
        result_type (type[T]): The desired return type. Defaults to ``str``.
        max_iterations: Maximum tool-call loop iterations for this agent.

    Returns:
        Callable[[str], Awaitable[T]]: An async function that takes a string
            argument 'instructions' and returns the specified type ``T``.

    """
    docstring = f"""
{description}

Args:
    instructions (str): The detailed instructions for the agent to follow. Including step by step plans if necessary.

Returns:
    {getattr(result_type, "__name__", str(result_type))}: The result returned by the agent after processing the instructions.
"""  # noqa: E501

    async def run_agent_as_tool(instructions: str) -> T:
        # DONT PROVIDE A DOCSTRING HERE
        model_options = get_model_options()
        effective_max_iterations = max_iterations
        if model_options and model_options.max_iterations is not None:
            effective_max_iterations = model_options.max_iterations
        agent = Agent(
            name=name,
            description=description,
            instruction=instruction,
            tools=tools,
            model=model_options.model if model_options and model_options.model else "",
            think=model_options.think if model_options and model_options.think is not None else False,
            persist_thinking=model_options.persist_thinking if model_options and model_options.persist_thinking is not None else True,
            options=model_options.to_options() if model_options else {},
            max_iterations=effective_max_iterations,
        )
        with agent_span(agent.name):
            history = ConversationHistory([
                {"role": "system", "content": agent.instruction},
                {"role": "user", "content": instructions},
            ])
            num_ctx = agent.options.get("num_ctx", 0) if agent.options else 0
            ctx_manager = ContextManager(
                history=history,
                context_limit=num_ctx,
                agent_name=agent.name,
                strategies=[SummarizeStrategy()],
            )
            hooks = default_hooks(
                agent,
                max_iterations=effective_max_iterations,
                ctx_manager=ctx_manager,
            )

            try:
                # For string results, single pass without retry
                if result_type is str:
                    return await _run_tool_loop_once(
                        history=history,
                        agent=agent,
                        hooks=hooks,
                    )  # type: ignore[return-value]

                # For non-string result types, retry the tool loop up to 5 times if JSON parse fails
                return await _run_with_json_retry(
                    history=history,
                    agent=agent,
                    result_type=result_type,
                    hooks=hooks,
                    max_attempts=5,
                )
            finally:
                # Collect sub-agent history for skill extraction
                collect_sub_agent_history(
                    agent_name=name,
                    parent_tool=func_name,
                    messages=history.messages,
                )

    # Give the tool function a deterministic, agent-derived name so the LLM can
    # distinguish multiple agent tools. We assume name values are unique.
    safe_agent_name = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_") or "agent"
    func_name = f"run_{safe_agent_name}_as_tool"
    run_agent_as_tool.__name__ = func_name
    run_agent_as_tool.__qualname__ = func_name
    run_agent_as_tool.__doc__ = docstring
    return run_agent_as_tool
