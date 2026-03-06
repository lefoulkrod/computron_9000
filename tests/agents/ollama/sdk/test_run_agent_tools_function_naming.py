"""Unit tests for agent tool function naming.

Verifies that make_run_agent_as_tool_function assigns a sanitized, agent-based
name to the returned function so the tool loop can distinguish multiple agents.
"""

import pytest
from pydantic import BaseModel

from agents.ollama.sdk.run_agent_tools import make_run_agent_as_tool_function


@pytest.mark.unit
async def test_function_name_derived_from_agent_name() -> None:
    """Ensure returned function name follows run_<agent>_as_tool pattern."""
    tool_func = make_run_agent_as_tool_function(
        name="My Fancy Agent",
        description="Test agent",
        instruction="Do things",
        tools=[],
    )

    # Expected sanitized name: spaces -> _, lowercase, pattern run_<name>_as_tool
    assert tool_func.__name__ == "run_my_fancy_agent_as_tool"
    assert tool_func.__qualname__ == "run_my_fancy_agent_as_tool"
    assert "Test agent" in (tool_func.__doc__ or "")


@pytest.mark.unit
async def test_function_name_fallback_when_name_empty() -> None:
    """If agent name sanitizes empty, fallback base becomes 'agent' in pattern."""
    func = make_run_agent_as_tool_function(
        name="***",
        description="X",
        instruction="Do things",
        tools=[],
    )
    assert func.__name__ == "run_agent_as_tool"


@pytest.mark.unit
async def test_docstring_contains_argument_description() -> None:
    """Docstring should include Args and Returns sections."""
    func = make_run_agent_as_tool_function(
        name="DocAgent",
        description="Doc agent description",
        instruction="Do things",
        tools=[],
    )
    doc = func.__doc__ or ""
    assert "Doc agent description" in doc
    assert "instructions (str)" in doc
    assert "Returns:" in doc


@pytest.mark.unit
async def test_docstring_exact_match() -> None:
    """Docstring should exactly match the template with provided description."""
    description = "Doc agent description"
    func = make_run_agent_as_tool_function(
        name="ExactDocAgent",
        description=description,
        instruction="Do things",
        tools=[],
    )

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

    func = make_run_agent_as_tool_function(
        name="DocTypeAgent",
        description="Doc type desc",
        instruction="Do things",
        tools=[],
        result_type=InlineModel,
    )
    doc = func.__doc__ or ""
    # Check the specific Returns line contains the dynamic type name
    assert "Returns:" in doc
    assert "\n    InlineModel: The result returned by the agent after processing the instructions.\n" in doc
