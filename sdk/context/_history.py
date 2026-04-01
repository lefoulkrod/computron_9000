"""Encapsulated conversation history with controlled mutation."""

import logging
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)


class ConversationHistory:
    """Wraps a message list with structured accessors and controlled mutation.

    The underlying list is never exposed for direct mutation. Code that needs
    the raw list for read-only purposes (e.g. passing to ``client.chat()``)
    can use the ``.messages`` property.
    """

    def __init__(
        self,
        messages: list[dict[str, Any]] | None = None,
        instance_id: str = "",
    ) -> None:
        self._messages: list[dict[str, Any]] = list(messages) if messages else []
        self.instance_id = instance_id

    # -- read-only access --------------------------------------------------

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Read-only snapshot of the message list."""
        return list(self._messages)

    @property
    def system_message(self) -> dict[str, Any] | None:
        """Return the system message if present, else *None*."""
        if self._messages and self._messages[0].get("role") == "system":
            return self._messages[0]
        return None

    @property
    def non_system_messages(self) -> list[dict[str, Any]]:
        """All messages except the leading system message."""
        if self._messages and self._messages[0].get("role") == "system":
            return list(self._messages[1:])
        return list(self._messages)

    # -- mutation ----------------------------------------------------------

    def append(self, message: dict[str, Any]) -> None:
        """Append a message to the history."""
        self._messages.append(message)

    def set_system_message(self, content: str) -> None:
        """Replace or insert the system message at index 0."""
        if self._messages and self._messages[0].get("role") == "system":
            self._messages[0] = {"role": "system", "content": content}
        else:
            self._messages.insert(0, {"role": "system", "content": content})

    def drop_range(self, start: int, end: int) -> None:
        """Remove messages in the half-open range ``[start, end)``.

        Raises:
            IndexError: If the range is out of bounds.
        """
        if start < 0 or end > len(self._messages) or start >= end:
            msg = "drop_range(%d, %d) out of bounds for history of length %d"
            raise IndexError(msg % (start, end, len(self._messages)))
        del self._messages[start:end]

    def insert(self, index: int, message: dict[str, Any]) -> None:
        """Insert a message at *index*.

        Raises:
            IndexError: If *index* is out of bounds.
        """
        if index < 0 or index > len(self._messages):
            msg = "insert(%d) out of bounds for history of length %d"
            raise IndexError(msg % (index, len(self._messages)))
        self._messages.insert(index, message)

    def get_mutable(self, index: int) -> dict[str, Any]:
        """Return a direct reference to the message at *index* for in-place mutation.

        Unlike ``messages`` (which returns copies), the returned dict IS the
        internal message — changes to it modify the history directly. Use
        this for lightweight mutations like clearing tool result content.
        """
        return self._messages[index]

    def clear(self) -> None:
        """Remove all messages."""
        self._messages.clear()

    def append_system_context(self, context: str) -> None:
        """Append temporary context to the system message.

        This modifies the system message in-place for the current turn only.
        The context is not persisted to conversation history.
        """
        if not self._messages:
            return

        # Find system message
        for msg in self._messages:
            if msg.get("role") == "system":
                # Append context if not already present
                current = msg.get("content", "")
                if context not in current:
                    msg["content"] = current + "\n\n" + context
                break

    # -- dunder helpers ----------------------------------------------------

    def __len__(self) -> int:
        return len(self._messages)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._messages)

    def __repr__(self) -> str:
        return "ConversationHistory(len=%d)" % len(self._messages)
