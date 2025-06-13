from google.adk.agents import SequentialAgent, LlmAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.models.lite_llm import LiteLlm
from tools.fs.fs import list_directory_contents, get_path_details, read_file_contents, search_files

from . import prompt

# litellm._turn_on_debug()

# Define the model as a module-level constant
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

computron_agent = LlmAgent(
    name="COMPUTRON_9000",
    model=LiteLlm(
        model=MODEL, 
    ),
    description=(
        "COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed to assist with a wide range of tasks."
    ),
    instruction=prompt.ROOT_AGENT_PROMPT,
    tools=[
        AgentTool(agent=file_system_agent,)
    ],
)

root_agent = SequentialAgent(
    name="RootAgent",
    sub_agents=[computron_agent],
)