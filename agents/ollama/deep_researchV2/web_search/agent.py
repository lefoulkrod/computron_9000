"""The agent for the web search functionality."""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_default_model
from tools.reddit import search_reddit
from tools.web import (
    search_google,
)

from .prompt import PROMPT

logger = logging.getLogger(__name__)

model = get_default_model()

web_search_agent = Agent(
    name="WEB_SEARCH_AGENT",
    description="An agent designed to perform web research using various tools.",
    instruction=PROMPT,
    model=model.model,
    options=model.options,
    tools=[
        search_google,
        search_reddit,
    ],
)

before_model_call_callback = make_log_before_model_call(web_search_agent)
after_model_call_callback = make_log_after_model_call(web_search_agent)
web_search_agent_tool = make_run_agent_as_tool_function(
    agent=web_search_agent,
    tool_description="""
    Search for information on the web from various sources, including Google and Reddit.
    """,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
