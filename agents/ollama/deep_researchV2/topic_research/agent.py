"""The agent for the topic research functionality."""

from agents.ollama.deep_researchV2.website_reader.agent import website_reader_agent_tool
from agents.ollama.sdk import make_run_agent_as_tool_function
from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
from tools.reddit import get_reddit_comments, get_reddit_submission

from .prompt import PROMPT

NAME = "TOPIC_RESEARCH_AGENT"
DESCRIPTION = "An agent designed to perform focused research on a specific topic."
SYSTEM_PROMPT = PROMPT
TOOLS = [
    website_reader_agent_tool,
    get_reddit_comments,
    get_reddit_submission,
    save_to_scratchpad,
    recall_from_scratchpad,
]

topic_research_agent_tool = make_run_agent_as_tool_function(
    name=NAME,
    description=DESCRIPTION,
    instruction=SYSTEM_PROMPT,
    tools=TOOLS,
)
