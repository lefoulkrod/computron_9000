import logging

from agents.ollama.sdk import Agent
from agents.prompt import WEB_AGENT_PROMPT
from config import load_config
from tools.web import search_google, get_webpage_substring, get_webpage_summary_sections

config = load_config()
logger = logging.getLogger(__name__)

web_agent: Agent = Agent(
    name="WEB_AGENT",
    description="WEB_AGENT is a simple agent designed to handle web-related tasks such as searching, browsing, and retrieving information from the web.",
    instruction=WEB_AGENT_PROMPT,
    model=config.llm.model,
    options={
        "num_ctx": config.llm.num_ctx,
    },
    tools=[
        get_webpage_summary_sections,
        get_webpage_substring,
        search_google,
    ],
)
