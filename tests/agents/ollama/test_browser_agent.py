import pytest

from agents.ollama.browser import browser_agent, browser_agent_tool
from tools.browser import (
    current_page,
    extract_text,
    fill_field,
    open_url,
    press_keys,
    scroll_page,
    ground_elements_by_text,
)
from tools.browser.interactions import click
from tools.browser.vision import ask_about_screenshot


@pytest.mark.unit
def test_browser_agent_basic_config() -> None:
    """Browser agent should expose all registered browsing tools in order."""
    assert browser_agent.name == "BROWSER_AGENT"
    assert browser_agent.tools and len(browser_agent.tools) == 9
    assert browser_agent.tools[0] is open_url
    assert browser_agent.tools[1] is click
    assert browser_agent.tools[2] is extract_text
    assert browser_agent.tools[3] is ask_about_screenshot
    assert browser_agent.tools[4] is ground_elements_by_text
    assert browser_agent.tools[5] is current_page
    assert browser_agent.tools[6] is fill_field
    assert browser_agent.tools[7] is press_keys
    assert browser_agent.tools[8] is scroll_page


@pytest.mark.unit
def test_browser_agent_tool_factory_name_and_doc() -> None:
    """Factory should expose a function with a descriptive name and docstring."""
    assert callable(browser_agent_tool)
    assert browser_agent_tool.__name__.startswith("run_browser_agent")
    assert browser_agent_tool.__doc__ is not None
