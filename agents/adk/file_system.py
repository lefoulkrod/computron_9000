"""File system agent definition."""

import logging
from typing import AsyncGenerator

from google.adk.agents import LlmAgent, SequentialAgent, BaseAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.genai import types

from .callbacks.callbacks import log_llm_request_callback, log_llm_response_callback
from tools.fs import list_directory_contents, get_path_details, read_file_contents, search_files, write_text_file
from agents.prompt import FILE_SYSTEM_AGENT_PROMPT
from config import load_config
from .model_utils import get_adk_model


logger = logging.getLogger(__name__)

MODEL = get_adk_model()

file_system_agent = LlmAgent(
    name="file_system",
    model=LiteLlm(
        model=MODEL,
    ),
    description="""
    An AI agent specialized in file system operations, including listing directory contents, retrieving file details, reading file contents, and searching for files.
    The agent will perform the requested file operations based on the provided instructions, which should describe the specific goal or outcome desired.
    The agent will not summarize the file contents or provide any additional information beyond the requested operations.
    """,
    instruction=FILE_SYSTEM_AGENT_PROMPT,
    tools=[
        list_directory_contents,
        get_path_details,
        read_file_contents,
        search_files,
        write_text_file
    ],
    after_model_callback=log_llm_response_callback,
    before_model_callback=[log_llm_request_callback],
)

async def run_filesystem_agent(instructions: str) -> str:
    """
    Executes the file system AI agent with the provided instructions.

    The instructions should be a detailed, step-by-step description of the file system operations to perform. The agent will interpret and execute these instructions as precisely as possible. Avoid vague or high-level requests; be explicit about each action to take.

    Args:
        instructions (str): Detailed, step-by-step instructions for the file system agent to carry out.

    Returns:
        str: The final result or output from the file system agent.

    Raises:
        ValueError: If instructions are not provided or are invalid.
        RuntimeError: If the agent fails to complete the task.
    """
    logger.debug("Running file system agent with instructions: %s", instructions)
    seq_agent = SequentialAgent(name="root", sub_agents=[file_system_agent])
    return await run_agent_with_result(seq_agent, instructions)

async def run_agent_with_result(agent: BaseAgent, instructions: str) -> str:
    """
    Runs the given agent with detailed, step-by-step instructions and returns the final result.

    The instructions should be a detailed, step-by-step description of the file system operations to perform. The agent will interpret and execute these instructions as precisely as possible. Avoid vague or high-level requests; be explicit about each action to take.

    Args:
        agent (LlmAgent): The agent instance to run.
        instructions (str): Detailed, step-by-step instructions for the agent to carry out.

    Returns:
        str: The final result or output from the agent.

    Raises:
        ValueError: If instructions are not provided or are invalid.
        RuntimeError: If the agent fails to complete the task.
    """
    DEFAULT_USER_ID = "filesystem"
    DEFAULT_SESSION_ID = "filesystem_session"
    APP_NAME = "computron_9000_filesystem"
    session_service = InMemorySessionService()
    if not instructions or not isinstance(instructions, str):
        logger.error("Instructions must be a non-empty string.")
        raise ValueError("Instructions must be a non-empty string.")
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    content = types.Content(role='user', parts=[types.Part(text=instructions)])
    generator: AsyncGenerator[Event, None] = runner.run_async(
        user_id=DEFAULT_USER_ID,
        session_id=DEFAULT_SESSION_ID,
        new_message=content
    )
    final_result = None
    async for event in generator:
        if event.content and event.content.parts and event.content.parts[0].text is not None:
            final_result = event.content.parts[0].text
        if event.is_final_response():
            break
    if final_result is None:
        logger.error("No result returned from agent.")
        raise RuntimeError("No result returned from agent.")
    return final_result

