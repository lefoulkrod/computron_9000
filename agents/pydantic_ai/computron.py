from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from agents.prompt import FILE_SYSTEM_AGENT_PROMPT
from tools.fs.fs import list_directory_contents

ollama_model = OpenAIModel(
    model_name="qwen3:32b",
    provider=OpenAIProvider(
        base_url="http://localhost:11434/v1",
    ),
    system_prompt_role="system",
    
)
agent = Agent(
    model = ollama_model,
    system_prompt=FILE_SYSTEM_AGENT_PROMPT,
    tools=[list_directory_contents],
)

result = agent.run_sync(
    "what files are in /home/larry",
)
print(result.output)
print(result.usage())