import pytest

from agents.adk.web import web_agent


def test_web_agent_tools_present():
    """
    Test that the web agent exposes the correct tools.
    """
    tool_names = {getattr(tool, 'name', getattr(tool, '__name__', str(tool))) for tool in web_agent.tools}
    assert any("get_webpage" in n for n in tool_names)
    assert any("search_google" in n for n in tool_names)
    assert any("playwright" in n for n in tool_names)


def test_web_agent_prompt():
    """
    Test that the web agent uses the correct prompt.
    """
    assert "web" in web_agent.instruction.lower()
    assert "navigate" in web_agent.instruction.lower()
    assert "summarize" in web_agent.instruction.lower()
