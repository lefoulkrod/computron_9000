# Standard library imports
import logging

# Third-party imports
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.agents.callback_context import CallbackContext

from agents.adk.callbacks import remove_thoughts_callback
from tools.web import get_webpage, html_find_elements, search_google
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
    An expert AI agent specialized in navigating the web including viewing web pages, navigating through websites, and downloading content from the internet.
    The agent will perform the requested web operations based on the provided instructions, which should describe the specific goal or outcome desired.
    The agent will return the results of the web operations without summarizing them unless explicitly requested to do so.
    """,
    instruction=WEB_AGENT_PROMPT,
    tools=[
        get_webpage,
        execute_nodejs_program_with_playwright,
        html_find_elements,
        search_google,
    ],
    after_model_callback=log_llm_response_callback,
    before_model_callback=[remove_thoughts_callback, log_llm_request_callback],
)
