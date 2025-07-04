import logging
from typing import Any, Callable, Dict, List

from pydantic import BaseModel

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
