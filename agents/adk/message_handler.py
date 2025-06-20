import os
from typing import AsyncGenerator, Sequence

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.adk.agent import root_agent
from agents.types import UserMessageEvent, Data

DEFAULT_USER_ID = "default_user"
DEFAULT_SESSION_ID = "default_session"
APP_NAME = "computron_9000"

_session_service = InMemorySessionService()

async def _ensure_session() -> object:
    """
    Retrieve or create a default session.

    Returns:
        object: The session object.
    """
    session = await _session_service.get_session(
        app_name=APP_NAME,
        user_id=DEFAULT_USER_ID,
        session_id=DEFAULT_SESSION_ID
    )
    if session is None:
        session = await _session_service.create_session(
            app_name=APP_NAME,
            user_id=DEFAULT_USER_ID,
            session_id=DEFAULT_SESSION_ID
        )
    return session

async def handle_user_message(message: str, data: Sequence[Data] | None = None, stream: bool = False) -> AsyncGenerator[UserMessageEvent, None]:
    """
    Handles user message with the agent runner, managing session and runner internally.

    Args:
        message (str): The user message to send to the agent.
        data (Sequence[Data] | None): Optional list of base64-encoded data and content type objects.
        stream (bool): Whether to stream responses (True) or return only the final response (False).

    Yields:
        UserMessageEvent: Contains the message and final flag.
            - If stream=True, yields one event per agent event.
            - If stream=False, yields only the final response event.
    """
    await _ensure_session()
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=_session_service
    )
    content = types.Content(role='user', parts=[types.Part(text=message)])
    # Optionally handle data (not yet used in logic)
    events = runner.run_async(
        user_id=DEFAULT_USER_ID,
        session_id=DEFAULT_SESSION_ID,
        new_message=content
    )
    if stream:
        async for event in events:
            if event.content and event.content.parts and event.content.parts[0].text is not None:
                yield UserMessageEvent(message=event.content.parts[0].text, final=event.is_final_response())
            if event.is_final_response():
                break
    else:
        final_response_text = "Agent did not produce a final response."
        async for event in events:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text is not None:
                    final_response_text = str(event.content.parts[0].text)
                elif event.actions and getattr(event.actions, 'escalate', False):
                    final_response_text = f"Agent escalated: {getattr(event, 'error_message', 'No specific message.')}"
                break
        yield UserMessageEvent(message=final_response_text or "Agent did not produce a final response.", final=True)
