# Standard library imports
"""File system agent definition."""

# Third-party imports
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

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
    instruction=FILE_SYSTEM_AGENT_PROMPT,
    tools=[
        list_directory_contents,
        get_path_details,
        read_file_contents,
        search_files
    ],
)

