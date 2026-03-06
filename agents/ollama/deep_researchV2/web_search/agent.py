"""The agent for the web search functionality."""

from agents.ollama.sdk import make_run_agent_as_tool_function
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.reddit import search_reddit
from tools.web import search_google

from .prompt import PROMPT

NAME = "WEB_SEARCH_AGENT"
DESCRIPTION = "An agent designed to perform web research using various tools."
SYSTEM_PROMPT = PROMPT
TOOLS = [
    search_google,
    search_reddit,
    save_to_scratchpad,
    recall_from_scratchpad,
]

web_search_agent_tool = make_run_agent_as_tool_function(
    name=NAME,
    description=DESCRIPTION,
    instruction=SYSTEM_PROMPT,
    tools=TOOLS,
)
