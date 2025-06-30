import logging
from typing import AsyncGenerator, Sequence, AsyncIterator, Iterator, Optional, Union, Tuple

from ollama import AsyncClient, ChatResponse

from agents.prompt import ROOT_AGENT_PROMPT
from agents.types import UserMessageEvent, Data
from config import load_config

logger = logging.getLogger(__name__)

config = load_config()

async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None,
    stream: bool = False
) -> AsyncGenerator[UserMessageEvent, None]:
    """
    Handles a user message by sending it to the LLM and yielding events.

    Args:
        message (str): The user's message.
        data (Sequence[Data] | None): Optional additional data.
        stream (bool): Whether to stream responses.

    Yields:
        UserMessageEvent: Events from the LLM.
    """
    system_message = {'role': 'system', 'content': ROOT_AGENT_PROMPT}
    send_message = {'role': 'user', 'content': message}
    client = AsyncClient()
    chat_args = {
        'model': config.llm.model,
        'messages': [system_message, send_message],
        
        'options': {
            "num_ctx": config.llm.num_ctx, 
        },
    }
    try:
        if stream:
            async for response, done in run_as_agent_stream(await client.chat(
                **chat_args,
                stream=True
            )):
                yield UserMessageEvent(
                    message=response or "",
                    final=done
                )
        else:
            response = run_as_agent(await client.chat(
                **chat_args,
                stream=False,
            ))
            yield UserMessageEvent(
                message=response or "",
                final=True
            )
    except Exception as exc:
        logger.exception(f"Error handling user message: {exc}")
        yield UserMessageEvent(message="An error occurred while processing your message.", final=True)

async def run_as_agent_stream(iterator: AsyncIterator[ChatResponse]) -> AsyncIterator[Tuple[Optional[str], bool]]:
    """
    Consumes an async iterator of ChatResponse and yields a tuple of (message content, done flag) as they are returned.

    Args:
        iterator (AsyncIterator[ChatResponse]): An async iterator yielding ChatResponse objects.

    Yields:
        Tuple[Optional[str], bool]: The message content from each ChatResponse object (or None) and the done flag.

    Raises:
        Exception: If an error occurs during iteration.
    """
    try:
        async for response in iterator:
            content = response.message.content
            done = response.done or False
            yield content, done
    except Exception as exc:
        logger.exception(f"Error running agent iterator: {exc}")
        raise

def run_as_agent(response: ChatResponse) -> Optional[str]:
    """
    Extracts the message content and done flag from a single ChatResponse.

    Args:
        response (ChatResponse): A ChatResponse object.

    Returns:
        Tuple[Optional[str], bool]: The message content (or None) and the done flag.
    """
    content = response.message.content
    return content