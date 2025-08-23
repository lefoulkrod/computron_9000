"""Tests for workflow verification using the code review agent.

Monkeypatches the code_review_agent_tool to return expected JSON shapes and
validates that _verify_step_result maps them correctly.
"""

import json

import pytest

from agents.ollama.coder import workflow as wf
from agents.ollama.coder.planner_agent.models import CommandSpec, PlanStep


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_step_result_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    step = PlanStep(id="s", title="t", step_kind="command", command=CommandSpec(run="true", timeout_sec=1))

    async def fake_tool(payload: str) -> str:  # type: ignore[override]
        data = json.loads(payload)
        assert "step" in data and "coder_output" in data
        return json.dumps({"pass": True, "fixes": []})

    monkeypatch.setattr(wf, "code_review_agent_tool", fake_tool)

    passed, details = await wf._verify_step_result(step=step, result="ok")

    assert passed is True
    assert details["passed"] is True
    assert details["fixes"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_step_result_fail_with_fixes(monkeypatch: pytest.MonkeyPatch) -> None:
    step = PlanStep(id="s", title="t", step_kind="file", file_path="a.py")

    async def fake_tool(payload: str) -> str:  # type: ignore[override]
        return json.dumps({"pass": False, "fixes": ["add tests", "export symbol"]})

    monkeypatch.setattr(wf, "code_review_agent_tool", fake_tool)

    passed, details = await wf._verify_step_result(step=step, result="did stuff")

    assert passed is False
    assert details["passed"] is False
    assert details["fixes"] == ["add tests", "export symbol"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_code_review_exception_bubbles_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the code review agent errors, it should bubble and stop the workflow."""

    step = PlanStep(id="s1", title="t", step_kind="command", command=CommandSpec(run="true", timeout_sec=1))

    async def fake_coder_agent_tool(_: str) -> str:  # type: ignore[override]
        return "ok"

    async def boom(_: str) -> str:  # type: ignore[override]
        raise RuntimeError("reviewer down")

    # Patch coder to succeed once and review to raise
    monkeypatch.setattr(wf, "coder_agent_tool", fake_coder_agent_tool)
    monkeypatch.setattr(wf, "code_review_agent_tool", boom)

    with pytest.raises(wf.CoderWorkflowAgentError):
        # Running the internal loop should propagate as CoderWorkflowAgentError
        out: list[wf.StepYield] = []
        async for item in wf._execute_steps_with_coder([step]):
            out.append(item)
