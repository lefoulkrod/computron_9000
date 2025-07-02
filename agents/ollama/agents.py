import logging
from typing import Any, Callable, Dict, List

from pydantic import BaseModel

from agents.prompt import ROOT_AGENT_PROMPT
from config import load_config
from tools.fs import list_directory_contents, read_file_contents, write_text_file

config = load_config()
logger = logging.getLogger(__name__)

class Agent(BaseModel):
    """
    Represents the configuration for a generic agent.

    Args:
        name (str): The agent's name.
        description (str): Description of the agent.
        instruction (str): The root prompt or instruction for the agent.
        model (str): The model name to use.
        options (Dict[str, Any]): Model options (e.g., num_ctx).
        tools (List[Callable[..., Any]]): List of callable tools available to the agent.
    """
    name: str
    description: str
    instruction: str
    model: str
    options: Dict[str, Any]
    tools: List[Callable[..., Any]]

computron: Agent = Agent(
    name="COMPUTRON_9000",
    description="COMPUTRON_9000 is a multi-modal multi-agent multi-model AI system designed to assist with a wide range of tasks.",
    instruction=ROOT_AGENT_PROMPT,
    model=config.llm.model,
    options={
        "num_ctx": config.llm.num_ctx,
    },
    tools=[
        list_directory_contents,
        read_file_contents,
        write_text_file,
    ],
)