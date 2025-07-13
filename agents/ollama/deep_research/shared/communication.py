"""Basic inter-agent communication primitives."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

logger = logging.getLogger(__name__)


class MessageBus:
    """Simple async message bus for agent communication."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def publish(self, message: dict[str, Any]) -> None:
        """Publish a message to the bus."""
        logger.debug("Publishing message: %s", message)
        await self._queue.put(message)

    async def subscribe(self) -> AsyncGenerator[dict[str, Any], None]:
        """Yield messages from the bus as they arrive."""
        while True:
            message = await self._queue.get()
            logger.debug("Received message: %s", message)
            yield message
            self._queue.task_done()
