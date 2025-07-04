import types
from typing import Callable


def make_agent_handoff_function(description: str) -> Callable[[str], str]:
    """
    Returns a function with the provided description as its docstring.

    Args:
        description (str): The docstring to assign to the returned function.

    Returns:
        Callable[[str], str]: A function that takes a string argument 'instructions' and returns a string, with the given docstring.
    """
    docstring = f"""
{description}

Args:
    instructions (str): The detailed instructions for the agent to follow.

Returns:
    str: The result returned by the agent after processing the instructions.
"""
    def run_agent_as_tool(instructions: str) -> str:
        # ...business logic here...
        return "Agent handoff complete."
    run_agent_as_tool.__doc__ = docstring
    return run_agent_as_tool
