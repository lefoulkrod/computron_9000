import pytest

from agents.ollama.browser import browser_agent, browser_agent_tool
from tools.browser.ask_about_screenshot import ask_about_screenshot
from tools.browser import open_url
from tools.browser.interactions import click


@pytest.mark.unit
def test_browser_agent_basic_config() -> None:
    """Browser agent should expose all registered browsing tools in order."""
    assert browser_agent.name == "BROWSER_AGENT"
    assert browser_agent.tools and len(browser_agent.tools) == 3
    assert browser_agent.tools[0] is open_url
    assert browser_agent.tools[1] is click
    assert browser_agent.tools[2] is ask_about_screenshot


@pytest.mark.unit
def test_browser_agent_tool_factory_name_and_doc() -> None:
    """Factory should expose a function with a descriptive name and docstring."""
    assert callable(browser_agent_tool)
    assert browser_agent_tool.__name__.startswith("run_browser_agent")
    assert browser_agent_tool.__doc__ is not None
