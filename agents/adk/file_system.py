from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from tools.fs.fs import list_directory_contents, get_path_details, read_file_contents, search_files
from agents.prompt import FILE_SYSTEM_AGENT_PROMPT
from config import load_config

MODEL = load_config().llm.model

file_system_agent = LlmAgent(
    name="file_system",
    model=LiteLlm(
        model=MODEL,
    ),
    description="""
    An an expert AI agent specialized in file and directory operations.
    The agent can make use of the following tools to assist with file system tasks:
    - `list_directory_contents`: List files and directories at a given path.
    - `get_path_details`: Get details about a file or directory (type, size, permissions, timestamps).
    - `read_file_contents`: Read or view the contents of a file.
    - `search_files`: Search for files using patterns or wildcards (glob matching).
    """,
    instruction=FILE_SYSTEM_AGENT_PROMPT,
    tools=[
        list_directory_contents,
        get_path_details,
        read_file_contents,
        search_files
    ],
)
