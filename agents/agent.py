from google.adk.agents import SequentialAgent, LlmAgent
from google.adk.models.lite_llm import LiteLlm
import litellm
from tools.fs.fs import list_directory_contents

from . import prompt

litellm._turn_on_debug()

computron_agent = LlmAgent(
    name="COMPUTRON_9000",
    model=LiteLlm(
        model="ollama_chat/qwen2.5-coder:32b_num_ctx_16k", 
        provider="ollama_chat"
    ),
    description=(
        "COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed to assist with a wide range of tasks."
    ),
    instruction=prompt.ROOT_AGENT_PROMPT,
    tools=[list_directory_contents],
)

root_agent = SequentialAgent(
    name="root_agent",
    sub_agents=[computron_agent]
)