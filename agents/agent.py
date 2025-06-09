from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
import litellm

from . import prompt

litellm._turn_on_debug()

root_agent = Agent(
    name="COMPUTRON_9000",
    model=LiteLlm(model="ollama_chat/qwen2.5-coder:32b_num_ctx_16k"),
    description=(
        "COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed to assist with a wide range of tasks."
    ),
    instruction=prompt.ROOT_AGENT_PROMPT,
)