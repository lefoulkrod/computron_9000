from typing import Callable, Any, Awaitable
from .agent import Agent
from .extract_thinking import split_think_content
from .tool_loop import run_tool_call_loop
import asyncio


def make_run_agent_as_tool_function(agent: Agent, tool_description: str) -> Callable[[str], Awaitable[str]]:
    """
    Returns a function that runs the given agent as a tool, with the provided description as its docstring.

    Args:
        agent (Agent): The agent to be run as a tool.
        tool_description (str): The docstring to assign to the returned function.

    Returns:
        Callable[[str], Awaitable[str]]: An async function that takes a string argument 'instructions' and returns a string, with the given docstring.
    """
    docstring = f"""
{tool_description}

Args:
    instructions (str): The detailed instructions for the agent to follow. Including step by step plans if necessary.

Returns:
    str: The result returned by the agent after processing the instructions.
"""
    async def run_agent_as_tool(instructions: str) -> str:
        # DONT PROVIDE A DOCSTRING HERE
        messages = [
            {"role": "system", "content": agent.instruction},
            {"role": "user", "content": instructions},
        ]
        result = ""
        try:
            gen = run_tool_call_loop(
                messages=messages,
                tools=agent.tools,
                model=agent.model,
                model_options=agent.options,
            )
            async for output in gen:
                main_text, _ = split_think_content(output)
                if main_text:
                    result += main_text + "\n"
        except Exception as exc:
            result = f"Error running agent tool loop: {exc}"
        return result.strip()

    run_agent_as_tool.__doc__ = docstring
    return run_agent_as_tool
