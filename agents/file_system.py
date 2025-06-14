from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from tools.fs.fs import list_directory_contents, get_path_details, read_file_contents, search_files
from . import prompt

MODEL = "ollama_chat/qwen3:32b"

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
