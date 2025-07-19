"""The agent for the topic research functionality."""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_default_model
from tools.reddit import get_reddit_comments_tree_shallow, get_reddit_submission
from tools.web import get_webpage_substring, get_webpage_summary_sections

from .prompt import PROMPT

logger = logging.getLogger(__name__)

model = get_default_model()

topic_research_agent = Agent(
    name="TOPIC_RESEARCH_AGENT",
    description="An agent designed to perform focused research on a specific topic.",
    instruction=PROMPT,
    model=model.model,
    options=model.options,
    tools=[
        get_webpage_summary_sections,
        get_webpage_substring,
        get_reddit_comments_tree_shallow,
        get_reddit_submission,
    ],
)

before_model_call_callback = make_log_before_model_call(topic_research_agent)
after_model_call_callback = make_log_after_model_call(topic_research_agent)
topic_research_agent_tool = make_run_agent_as_tool_function(
    agent=topic_research_agent,
    tool_description="""
    Download and analyze content from specified URLs related to a research topic.
    """,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
