import logging

from agents.ollama.sdk import (
    Agent,
    make_run_agent_as_tool_function,
    make_log_before_model_call,
    make_log_after_model_call,
)
from config import load_config
from tools.web import search_google, get_webpage_substring, get_webpage_summary_sections, search_reddit

WEB_AGENT_NAME = "WEB_AGENT"
WEB_AGENT_DESCRIPTION = """
WEB_AGENT is a specialized agent designed to do provide deep research based on the latest information available on the web.
WEB_AGENT has access to popular sources like Google and Reddit as well as the rest of the open web.
"""
WEB_AGENT_PROMPT = """
You are WEB_AGENT, an expert at doing research based on information found on the web.
# Research Steps
1. Use all of the available tools to perform extensive research when answering questions.
2. First, search broadly for information on the topic being asked about.
3. Second, use select the most relevant search results.
4. Navigate to the content of each search result and to get more detailed information.
5. Summarize the research results.
6. You may need to use multiple tools to gather all the information you need.
7. Always cite your sources, return links to the sources you used in your response.
8. If code samples are provided, return them unsummarized.
"""

config = load_config()
logger = logging.getLogger(__name__)

web_agent: Agent = Agent(
    name=WEB_AGENT_NAME,
    description=WEB_AGENT_DESCRIPTION,
    instruction=WEB_AGENT_PROMPT,
    model=config.llm.model,
    options={
        "num_ctx": config.llm.num_ctx,
    },
    tools=[
        get_webpage_summary_sections,
        get_webpage_substring,
        search_google,
        search_reddit,
    ],
)

web_agent_before_callback = make_log_before_model_call(web_agent)
web_agent_after_callback = make_log_after_model_call(web_agent)

web_agent_tool = make_run_agent_as_tool_function(
    agent=web_agent,
    tool_description=WEB_AGENT_DESCRIPTION,
    before_model_callbacks=[web_agent_before_callback],
    after_model_callbacks=[web_agent_after_callback],
)

__all__ = [
    "web_agent",
    "web_agent_before_callback",
    "web_agent_after_callback",
    "web_agent_tool",
]
