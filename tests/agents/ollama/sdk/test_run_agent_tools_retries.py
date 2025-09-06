import json
from typing import Any

import pytest

from agents.ollama.sdk.run_agent_tools import (
    AgentToolConversionError,
    make_run_agent_as_tool_function,
)
from agents.types import Agent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_json_parse_retries_then_succeeds(monkeypatch):
    """Simulate transient JSON parse failures that recover before max attempts."""

    payload = {"ok": True}

    async def fake_loop(**_: Any):
        yield json.dumps(payload), None

    import agents.ollama.sdk.run_agent_tools as mod

    # Patch the symbol in the target module
    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    # Monkeypatch json.loads to fail the first 3 times, then succeed
    call_count = {"n": 0}
    real_loads = json.loads

    def flaky_loads(s: str, *args: Any, **kwargs: Any):
        call_count["n"] += 1
        if call_count["n"] < 4:
            raise json.JSONDecodeError("boom", s, 0)
        return real_loads(s, *args, **kwargs)

    monkeypatch.setattr(mod.json, "loads", flaky_loads)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )

    tool_fn = make_run_agent_as_tool_function(agent, "Retries", result_type=dict)
    res = await tool_fn("x")
    assert res == payload
    # ensure we actually retried
    assert call_count["n"] == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_json_parse_retry_exhaustion_raises(monkeypatch):
    """If all 5 attempts fail, surface AgentToolConversionError."""

    content = "{not really json}"

    async def fake_loop(**_: Any):
        yield content, None

    import agents.ollama.sdk.run_agent_tools as mod

    monkeypatch.setattr(mod, "run_tool_call_loop", fake_loop)

    # Always fail loads
    def always_fail(s: str, *args: Any, **kwargs: Any):
        raise json.JSONDecodeError("nope", s, 0)

    monkeypatch.setattr(mod.json, "loads", always_fail)

    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )

    tool_fn = make_run_agent_as_tool_function(agent, "Retries", result_type=dict)
    with pytest.raises(AgentToolConversionError):
        await tool_fn("x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_loop_is_rerun_each_retry(monkeypatch):
    """Assert the tool loop is invoked once per retry attempt on non-JSON results."""

    payload = {"ok": True}

    # Count tool loop invocations
    loop_calls = {"n": 0}

    async def counting_fake_loop(**_: Any):
        loop_calls["n"] += 1
        # Always yield valid JSON payload; the retry will be triggered by loads failing
        yield json.dumps(payload), None

    import agents.ollama.sdk.run_agent_tools as mod

    # Patch the symbol in the target module
    monkeypatch.setattr(mod, "run_tool_call_loop", counting_fake_loop)

    # Fail json.loads for the first 2 attempts, then succeed.
    # This should cause exactly 3 total tool loop invocations.
    loads_calls = {"n": 0}
    real_loads = json.loads

    def flaky_loads(s: str, *args: Any, **kwargs: Any):
        loads_calls["n"] += 1
        if loads_calls["n"] <= 2:
            raise json.JSONDecodeError("boom", s, 0)
        return real_loads(s, *args, **kwargs)

    monkeypatch.setattr(mod.json, "loads", flaky_loads)

    agent = Agent(
        name="Retry Counter Agent",
        description="desc",
        instruction="do it",
        model="dummy",
        options={},
        tools=[],
    )

    tool_fn = make_run_agent_as_tool_function(agent, "Retries", result_type=dict)
    res = await tool_fn("instructions")

    assert res == payload
    # 2 failures -> 2 retries + 1 final success = 3 tool loop runs
    assert loop_calls["n"] == 3
