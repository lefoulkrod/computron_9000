"""Unit tests for agent tool function naming.

Verifies that make_run_agent_as_tool_function assigns a sanitized, agent-based
name to the returned function so the tool loop can distinguish multiple agents.
"""

from collections.abc import Callable

import pytest
from pydantic import BaseModel

from agents.types import Agent
from agents.ollama.sdk.run_agent_tools import make_run_agent_as_tool_function


@pytest.mark.unit
async def test_function_name_derived_from_agent_name() -> None:
    """Ensure returned function name follows run_<agent>_as_tool pattern."""
    agent = Agent(
        name="My Fancy Agent",
        description="desc",
        instruction="Do things",
        model="dummy-model",
        options={},
        tools=[],
        think=False,
    )

    tool_func = make_run_agent_as_tool_function(agent=agent, tool_description="Test agent")

    # Expected sanitized name: spaces -> _, lowercase, pattern run_<name>_as_tool
    assert tool_func.__name__ == "run_my_fancy_agent_as_tool"
    assert tool_func.__qualname__ == "run_my_fancy_agent_as_tool"
    assert "Test agent" in (tool_func.__doc__ or "")


@pytest.mark.unit
async def test_function_name_fallback_when_name_empty() -> None:
    """If agent name sanitizes empty, fallback base becomes 'agent' in pattern."""
    agent = Agent(
        name="***",
        description="desc",
        instruction="Do things",
        model="dummy-model",
        options={},
        tools=[],
        think=False,
    )

    func = make_run_agent_as_tool_function(agent=agent, tool_description="X")
    assert func.__name__ == "run_agent_as_tool"


@pytest.mark.unit
async def test_docstring_contains_argument_description() -> None:
    """Docstring should include Args and Returns sections."""
    agent = Agent(
        name="DocAgent",
        description="desc",
        instruction="Do things",
        model="dummy-model",
        options={},
        tools=[],
        think=False,
    )

    func = make_run_agent_as_tool_function(agent=agent, tool_description="Doc agent description")
    doc = func.__doc__ or ""
    assert "Doc agent description" in doc
    assert "instructions (str)" in doc
    assert "Returns:" in doc


@pytest.mark.unit
async def test_docstring_exact_match() -> None:
    """Docstring should exactly match the template with provided description."""
    agent = Agent(
        name="ExactDocAgent",
        description="desc",
        instruction="Do things",
        model="dummy-model",
        options={},
        tools=[],
        think=False,
    )

    description = "Doc agent description"
    func = make_run_agent_as_tool_function(agent=agent, tool_description=description)

    expected = (
        "\n"
        "Doc agent description\n"
        "\n"
        "Args:\n"
        "    instructions (str): The detailed instructions for the agent to follow. Including step by step plans if necessary.\n"
        "\n"
        "Returns:\n"
        "    str: The result returned by the agent after processing the instructions.\n"
    )

    assert func.__doc__ == expected


@pytest.mark.unit
async def test_docstring_dynamic_return_type() -> None:
    """Docstring 'Returns' section should reflect the provided result_type name."""

    class InlineModel(BaseModel):
        foo: int

    agent = Agent(
        name="DocTypeAgent",
        description="desc",
        instruction="Do things",
        model="dummy-model",
        options={},
        tools=[],
        think=False,
    )

    func = make_run_agent_as_tool_function(
        agent=agent, tool_description="Doc type desc", result_type=InlineModel
    )
    doc = func.__doc__ or ""
    # Check the specific Returns line contains the dynamic type name
    assert "Returns:" in doc
    assert "\n    InlineModel: The result returned by the agent after processing the instructions.\n" in doc
