"""Agent for reviewing coder outputs and giving accept/reject feedback with guidance."""

import logging

from agents.ollama.sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    make_run_agent_as_tool_function,
)
from agents.types import Agent
from models import get_model_by_name

logger = logging.getLogger(__name__)


model = get_model_by_name("coder_architect")


REVIEWER_SYSTEM_PROMPT = """
You are an expert software architect. You will receive a software assignment. Your job
is to complete the assignment in cooperation with a coder agent. You will receive the
assignment give to the coder agent as well as the result of its work. You will accept or
reject the work. If you accept the work just return the word `accepted`. If you reject
return the word `rejected` and give updated instructions for the coder agent
to follow.
"""


reviewer_agent = Agent(
    name="REVIEWER_AGENT",
    description="Reviews coder results; returns 'accepted' or 'rejected' with actionable guidance.",
    instruction=REVIEWER_SYSTEM_PROMPT,
    model=model.model,
    options=model.options,
    tools=[],
    think=model.think,
)

before_model_call_callback = make_log_before_model_call(reviewer_agent)
after_model_call_callback = make_log_after_model_call(reviewer_agent)
reviewer_agent_tool = make_run_agent_as_tool_function(
    agent=reviewer_agent,
    tool_description="""
    Review coder output and decide acceptance; provide revisions when necessary.
    """,
    before_model_callbacks=[before_model_call_callback],
    after_model_callbacks=[after_model_call_callback],
)
