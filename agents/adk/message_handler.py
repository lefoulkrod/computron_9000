from typing import AsyncGenerator
from google.adk.runners import Runner
from google.genai import types
from pydantic import BaseModel

DEFAULT_USER_ID = "default_user"
DEFAULT_SESSION_ID = "default_session"

class UserMessageEvent(BaseModel):
    """
    Represents a message event from the agent.

    Attributes:
        message (str): The message content from the agent.
        final (bool): Whether this is the final response in the sequence.
    """
    message: str
    final: bool

async def handle_user_message(message: str, runner: Runner, stream: bool) -> AsyncGenerator[UserMessageEvent, None]:
    """
    Handles user message with the agent runner.

    Args:
        message (str): The user message to send to the agent.
        runner (Runner): The agent runner instance.
        stream (bool): Whether to stream responses (True) or return only the final response (False).

    Yields:
        UserMessageEvent: Contains the message and final flag.
            - If stream=True, yields one event per agent event.
            - If stream=False, yields only the final response event.
    """
    content = types.Content(role='user', parts=[types.Part(text=message)])
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
