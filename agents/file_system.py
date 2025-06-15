# Standard library imports

# Third-party imports
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

# Local imports
from tools.fs.fs import list_directory_contents, get_path_details, read_file_contents, search_files
from . import prompt
from config import load_config

MODEL = load_config().llm.model

file_system_agent = LlmAgent(
    name="FileSystem",
    model=LiteLlm(
        model=MODEL,
    ),
    description="FileSystem is an expert AI agent specialized in file and directory operations.",
    instruction=prompt.FILE_SYSTEM_AGENT_PROMPT,
    tools=[
        list_directory_contents,
        get_path_details,
        read_file_contents,
        search_files
    ],
)
