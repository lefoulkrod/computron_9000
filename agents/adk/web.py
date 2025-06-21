# Standard library imports
"""Web agent definition."""

# Third-party imports
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from tools.web.get_webpage import get_webpage
from tools.web.search_google import search_google
from tools.code.execute_code import execute_nodejs_program_with_playwright
from agents.prompt import WEB_AGENT_PROMPT
from config import load_config
from . import get_adk_model

MODEL = get_adk_model()

web_agent = LlmAgent(
    name="web",
    model=LiteLlm(
        model=MODEL,
    ),
    description="""
    An expert AI agent specialized in web navigation, search, and summarization. 
    The agent can use the following tools to assist with web-based tasks:
    - `get_webpage`: Fetch and extract content from a web page.
    - `execute_nodejs_program_with_playwright`: Run Node.js scripts with Playwright for advanced web automation and multi-step workflows.
    """,
    instruction=WEB_AGENT_PROMPT,
    tools=[
        get_webpage,
        execute_nodejs_program_with_playwright
    ],
)
