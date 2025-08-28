import asyncio
import json
from typing import Any

import pytest
from pydantic import BaseModel

from agents.ollama.sdk.run_agent_tools import (
    AgentToolConversionError,
    make_run_agent_as_tool_function,
)
from agents.types import Agent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_agent_as_tool_returns_string_by_default(monkeypatch):
    """Factory returns an async tool that yields concatenated string when no type specified."""

    async def fake_loop(**_: Any):
        yield "hello", None
        yield "world", None

    # Patch the symbol in the target module
    import agents.ollama.sdk.run_agent_tools as mod

    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )
    tool_fn = make_run_agent_as_tool_function(agent, "Echo")
    result = await tool_fn("say something")
    assert result == "hello\nworld"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_agent_as_tool_dict_conversion(monkeypatch):
    """When a dict result_type is requested, JSON is parsed and returned as dict."""

    payload = {"a": 1, "b": "x"}

    async def fake_loop(**_: Any):
        yield json.dumps(payload), None

    import agents.ollama.sdk.run_agent_tools as mod

    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )
    tool_fn = make_run_agent_as_tool_function(agent, "To dict", result_type=dict)
    result = await tool_fn("return dict")
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_agent_as_tool_list_conversion(monkeypatch):
    """List conversion should parse JSON into a Python list."""

    payload = [1, 2, 3]

    async def fake_loop(**_: Any):
        yield json.dumps(payload), None

    import agents.ollama.sdk.run_agent_tools as mod

    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )
    tool_fn = make_run_agent_as_tool_function(agent, "To list", result_type=list)
    result = await tool_fn("return list")
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_agent_as_tool_pydantic_model_conversion(monkeypatch):
    """Pydantic model conversion should parse JSON and validate into the model class."""

    payload = {"base64_encoded": "Zm9v", "content_type": "text/plain"}

    class InlineModel(BaseModel):
        base64_encoded: str
        content_type: str

    async def fake_loop(**_: Any):
        yield json.dumps(payload), None

    import agents.ollama.sdk.run_agent_tools as mod

    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )
    tool_fn = make_run_agent_as_tool_function(agent, "To model", result_type=InlineModel)
    result = await tool_fn("return model")
    assert isinstance(result, InlineModel)
    assert result.base64_encoded == payload["base64_encoded"]
    assert result.content_type == payload["content_type"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_agent_as_tool_invalid_json_raises(monkeypatch):
    """Invalid JSON with non-string type should raise AgentToolConversionError."""

    async def fake_loop(**_: Any):
        yield "not json", None

    import agents.ollama.sdk.run_agent_tools as mod

    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )
    tool_fn = make_run_agent_as_tool_function(agent, "To dict", result_type=dict)
    with pytest.raises(AgentToolConversionError):
        await tool_fn("return dict")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scalar_conversions_int_float_bool(monkeypatch):
    """Support JSON scalar conversions to int/float/bool via result_type."""

    async def fake_loop_int(**_: Any):
        yield "123", None

    async def fake_loop_float(**_: Any):
        yield "3.14", None

    async def fake_loop_bool_true(**_: Any):
        yield "true", None

    import agents.ollama.sdk.run_agent_tools as mod

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )

    # int
    mod.run_tool_call_loop = fake_loop_int  # type: ignore[assignment]
    tool_fn = make_run_agent_as_tool_function(agent, "To int", result_type=int)
    assert await tool_fn("return int") == 123

    # float
    mod.run_tool_call_loop = fake_loop_float  # type: ignore[assignment]
    tool_fn = make_run_agent_as_tool_function(agent, "To float", result_type=float)
    assert await tool_fn("return float") == 3.14

    # bool
    mod.run_tool_call_loop = fake_loop_bool_true  # type: ignore[assignment]
    tool_fn = make_run_agent_as_tool_function(agent, "To bool", result_type=bool)
    assert await tool_fn("return bool") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_or_whitespace_with_non_str_type_raises(monkeypatch):
    """Whitespace content should fail JSON parsing when non-str type requested."""

    async def fake_loop(**_: Any):
        yield "   \n\t  ", None

    import agents.ollama.sdk.run_agent_tools as mod
    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )
    tool_fn = make_run_agent_as_tool_function(agent, "To dict", result_type=dict)
    with pytest.raises(AgentToolConversionError):
        await tool_fn("return dict")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_callbacks_wiring(monkeypatch):
    """Ensure before/after callbacks are passed to the loop and invoked."""

    seen = {"before": 0, "after": 0}

    def before_cb(msgs):  # noqa: ANN001 - tests flexible signature
        seen["before"] += 1

    def after_cb(resp):  # noqa: ANN001 - tests flexible signature
        seen["after"] += 1

    async def fake_loop(**kwargs: Any):
        # Simulate callback invocation by calling provided callbacks
        for cb in kwargs.get("before_model_callbacks", []) or []:
            cb([{"role": "user", "content": "x"}])
        for cb in kwargs.get("after_model_callbacks", []) or []:
            cb(object())
        yield json.dumps({"ok": True}), None

    import agents.ollama.sdk.run_agent_tools as mod
    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )
    tool_fn = make_run_agent_as_tool_function(
        agent,
        "Callbacks",
        result_type=dict,
        before_model_callbacks=[before_cb],
        after_model_callbacks=[after_cb],
    )
    res = await tool_fn("x")
    assert res == {"ok": True}
    assert seen["before"] == 1
    assert seen["after"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_exception_propagation(monkeypatch):
    """Exceptions from the loop should surface unchanged from the wrapper."""

    class Boom(Exception):
        pass

    async def fake_loop(**_: Any):
        # Return an async generator that raises on first iteration to match the
        # async-iterator contract expected by the wrapper.
        raise Boom("nope")
        if False:  # pragma: no cover - ensure it's recognized as an async generator
            yield None, None

    import agents.ollama.sdk.run_agent_tools as mod
    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )
    tool_fn = make_run_agent_as_tool_function(agent, "Err", result_type=dict)
    with pytest.raises(Boom):
        await tool_fn("x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_agent_as_tool_list_of_pydantic_models(monkeypatch):
    """JSON array should validate into list[Model] when result_type is list[Model]."""

    class Item(BaseModel):
        id: int
        name: str

    payload = [
        {"id": 1, "name": "a"},
        {"id": 2, "name": "b"},
    ]

    async def fake_loop(**_: Any):
        yield json.dumps(payload), None

    import agents.ollama.sdk.run_agent_tools as mod
    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )

    tool_fn = make_run_agent_as_tool_function(agent, "To list of models", result_type=list[Item])
    result = await tool_fn("return list of models")
    assert isinstance(result, list)
    assert all(isinstance(x, Item) for x in result)
    assert [x.id for x in result] == [1, 2]
    assert [x.name for x in result] == ["a", "b"]
