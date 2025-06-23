# Standard library imports
"""File system agent definition."""

# Third-party imports
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from agents.adk.callbacks.callbacks import log_llm_request_callback, log_llm_response_callback
from tools.fs.fs import list_directory_contents, get_path_details, read_file_contents, search_files
from agents.prompt import FILE_SYSTEM_AGENT_PROMPT
from config import load_config
from . import get_adk_model

MODEL = get_adk_model()

file_system_agent = LlmAgent(
    name="file_system",
    model=LiteLlm(
        model=MODEL,
    ),
    description="""
    An AI agent specialized in file system operations, including listing directory contents, retrieving file details, reading file contents, and searching for files.
    The agent will perform the requested file operations based on the provided instructions, which should describe the specific goal or outcome desired.
    The agent will not summarize the file contents or provide any additional information beyond the requested operations.
    """,
    instruction=FILE_SYSTEM_AGENT_PROMPT,
    tools=[
        list_directory_contents,
        get_path_details,
        read_file_contents,
        search_files
    ],
    after_model_callback=log_llm_response_callback,
    before_model_callback=[log_llm_request_callback],
)

