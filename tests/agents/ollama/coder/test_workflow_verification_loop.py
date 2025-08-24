"""Unit tests for coder workflow verification loop.

Verifies that each step re-runs until verification passes. We monkeypatch the
verification stub to simulate failing then passing, and the coder agent to
return different outputs per attempt.
"""

from typing import Any

import pytest

from agents.ollama.coder.planner_agent.models import CommandSpec, PlanStep
from agents.ollama.coder import workflow as wf


@pytest.mark.unit
@pytest.mark.asyncio
async def test_step_retries_until_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single step should retry until verification returns True.

    We simulate two failed verifications followed by a pass on the third try.
    """

    # Step definition
    step = PlanStep(
        id="s1",
        title="Do something",
        step_kind="command",
        command=CommandSpec(run="echo hi", timeout_sec=1),
        implementation_details=[],
        depends_on=[],
    )

    # Track calls
    coder_calls: list[str] = []
    verify_calls: list[dict[str, Any]] = []

    async def fake_coder_agent_tool(payload: str) -> str:  # type: ignore[override]
        coder_calls.append(payload)
        return f"run#{len(coder_calls)}"

    # Inject the fake coder agent
    monkeypatch.setattr(wf, "coder_agent_tool", fake_coder_agent_tool)

    # Make verification fail twice then pass
    state = {"count": 0}

    async def fake_verify(*, step: PlanStep, result: str):
        state["count"] += 1
        verify_calls.append({"result": result, "count": state["count"]})
        return (state["count"] >= 3, [])

    monkeypatch.setattr(wf, "_verify_step_result", fake_verify)

    # Execute
    out: list[wf.StepYield] = []
    async for item in wf._execute_steps_with_coder([step]):
        out.append(item)

    # Assertions
    assert len(out) == 1
    assert out[0]["completed"] is True
    assert state["count"] == 3  # two fails, one pass
    assert len(coder_calls) == 3  # coder re-runs 3 times
    # Ensure the final result surfaced is the last coder output
    assert out[0]["result"] == "run#3"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fixes_are_passed_on_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """When verification fails, the required_changes should be passed back as fixes.

    We check that the second coder call contains a JSON payload with a "fixes" field
    equal to the list produced by the first failed verification.
    """

    step = PlanStep(
        id="s1",
        title="Do something",
        step_kind="command",
        command=CommandSpec(run="echo hi", timeout_sec=1),
        implementation_details=[],
        depends_on=[],
    )

    # Capture coder payloads
    coder_payloads: list[str] = []

    async def fake_coder_agent_tool(payload: str) -> str:  # type: ignore[override]
        coder_payloads.append(payload)
        return "result"

    monkeypatch.setattr(wf, "coder_agent_tool", fake_coder_agent_tool)

    # First verification fails with fixes; second passes
    calls = {"n": 0}

    async def fake_verify(*, step: PlanStep, result: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return (False, ["fix-1", "fix-2"])  # provide fixes on failure
        return (True, [])

    monkeypatch.setattr(wf, "_verify_step_result", fake_verify)

    # Run one step
    out: list[wf.StepYield] = []
    async for item in wf._execute_steps_with_coder([step]):
        out.append(item)

    # Two coder calls expected due to one retry
    assert len(coder_payloads) == 2

    # The second payload should include fixes
    import json as _json

    first = _json.loads(coder_payloads[0])
    second = _json.loads(coder_payloads[1])
    assert "fixes" not in first
    assert second.get("fixes") == ["fix-1", "fix-2"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependencies_are_collected_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure dependency collection works and coder still loops on verification.

    We create a small dependency chain and make verification pass immediately to
    avoid multiple reruns here.
    """

    sA = PlanStep(id="A", title="A", step_kind="command", command=CommandSpec(run="true", timeout_sec=1))
    sB = PlanStep(id="B", title="B", depends_on=["A"], step_kind="command", command=CommandSpec(run="true", timeout_sec=1))

    calls: list[str] = []

    async def fake_coder_agent_tool(payload: str) -> str:  # type: ignore[override]
        calls.append(payload)
        return "ok"

    async def fake_verify(*, step: PlanStep, result: str):
        return (True, [])

    monkeypatch.setattr(wf, "coder_agent_tool", fake_coder_agent_tool)
    monkeypatch.setattr(wf, "_verify_step_result", fake_verify)

    out: list[wf.StepYield] = []
    async for item in wf._execute_steps_with_coder([sA, sB]):
        out.append(item)

    assert [o["step_id"] for o in out] == ["A", "B"]
    # 2 coder calls, one per step
    assert len(calls) == 2
