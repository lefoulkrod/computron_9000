import inspect

import pytest

from agents.ollama.browser import browser_agent
from tools.browser import extract_text, fill_field


@pytest.mark.unit
def test_browser_agent_includes_extract_text_tool() -> None:
    """Agent tools list should include the extract_text callable."""
    tool_funcs = set(browser_agent.tools)
    # Compare by underlying function object (not name only) to avoid false positives
    assert any(t is extract_text for t in tool_funcs), "extract_text not registered in browser agent tools"
    assert any(t is fill_field for t in tool_funcs), "fill_field not registered in browser agent tools"
    # Basic sanity: all tools are callables
    assert all(callable(t) for t in tool_funcs)
    # Ensure docstring mention if we rely on SYSTEM_PROMPT embedding (optional heuristic)
    prompt = browser_agent.instruction
    assert "extract_text" in prompt
    assert "fill_field" in prompt
