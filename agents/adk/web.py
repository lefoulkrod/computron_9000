# Standard library imports
import logging

# Third-party imports
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from tools.web import get_webpage_summary, html_find_elements, search_google
from tools.code.execute_code import execute_nodejs_program_with_playwright
from agents.prompt import WEB_AGENT_PROMPT
from . import get_adk_model
from .callbacks import log_llm_response_callback, log_llm_request_callback

logger = logging.getLogger(__name__)

MODEL = get_adk_model()

web_agent = LlmAgent(
    name="web",
    model=LiteLlm(
        model=MODEL,
    ),
    description="""
    An expert AI agent specialized in navigating the web including searching, navigating, and downloading content from the internet.
    The agent will perform the requested web operations based on the provided instructions, which should describe the specific goal or outcome desired.
    The agent will return the results of the web operations without summarizing them unless explicitly requested to do so.
    Provide explicit and detailed instructions for the agent to follow including whether or not to summarize the results.
    Provide all context necessary for the agent to perform the task, including any specific URLs, search queries, or other relevant information.
    DO NOT assume the agent has any prior knowledge or context about the task beyond what is provided in the instructions.
    """,
    instruction=WEB_AGENT_PROMPT,
    tools=[
        get_webpage_summary,
        execute_nodejs_program_with_playwright,
        html_find_elements,
        search_google,
    ],
    after_model_callback=log_llm_response_callback,
    before_model_callback=[log_llm_request_callback],
)

