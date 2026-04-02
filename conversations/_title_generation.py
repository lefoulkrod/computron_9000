"""Title generation for conversations.

This module handles generating descriptive titles for conversations
based on the user's first message. It uses the configured summary model
to generate concise titles (3-5 words) that capture the essence of the conversation.
"""

import logging

from config import load_config
from sdk.providers import get_provider

logger = logging.getLogger(__name__)

# System prompt for generating conversation titles
_TITLE_GENERATION_PROMPT = """You are a helpful assistant that generates short, descriptive titles for conversations.
Given a user's first message, generate a concise title (3-5 words max) that captures the essence of the conversation.
Return ONLY the title text, with no quotes, no formatting, and no explanation.
"""


async def generate_conversation_title(first_message: str) -> str:
    """Generate a descriptive title for a conversation based on the first message.
    
    Uses the configured summary model to generate a concise title.
    Falls back to a truncated version of the first message if generation fails.
    
    Args:
        first_message: The first message from the user.
        
    Returns:
        A generated title string (3-5 words recommended).
    """
    try:
        cfg = load_config()
        
        # Check if summary model is configured
        if cfg.summary is None or not cfg.summary.model:
            logger.debug("No summary model configured, skipping title generation")
            return _truncate_for_title(first_message)
        
        provider = get_provider()
        
        # Prepare messages for title generation
        messages = [
            {"role": "system", "content": _TITLE_GENERATION_PROMPT},
            {"role": "user", "content": f"Generate a title for this conversation: {first_message}"}
        ]
        
        # Get model options from config, limit output to ~50 tokens
        options = cfg.summary.options.copy() if cfg.summary.options else {}
        options["num_predict"] = 50
        options["temperature"] = min(options.get("temperature", 0.3), 0.5)  # Keep it focused
        
        # Generate title using the summary model
        response = await provider.chat(
            model=cfg.summary.model,
            messages=messages,
            options=options,
            think=False,
        )
        
        if response and response.message and response.message.content:
            # Clean up the generated title
            title = response.message.content.strip()
            # Remove surrounding quotes if present
            title = title.strip('"\'').strip()
            # Limit length
            if len(title) > 80:
                title = title[:77] + "..."
            
            if title:
                logger.info("Generated title: %r", title)
                return title
        
        logger.warning("Empty response from title generation model, using fallback")
        return _truncate_for_title(first_message)
        
    except Exception:
        logger.exception("Error generating conversation title")
        return _truncate_for_title(first_message)


def _truncate_for_title(message: str, max_length: int = 50) -> str:
    """Truncate a message to create a fallback title.
    
    Args:
        message: The message to truncate.
        max_length: Maximum length for the title.
        
    Returns:
        Truncated message suitable as a title.
    """
    # Remove newlines and extra spaces
    clean = " ".join(message.split())
    if len(clean) > max_length:
        return clean[:max_length - 3] + "..."
    return clean



