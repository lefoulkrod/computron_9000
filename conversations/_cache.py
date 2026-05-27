"""Bounded LRU of in-memory ``Conversation`` objects.

Each channel/handler owns one. The on-disk conversation store is
authoritative; the cache exists so consecutive turns within the same
conversation don't re-read ``history.json`` every time, and so the
``PersistenceHook``'s in-place mutations of history land in something
the next turn reuses.

Eviction is LRU but skips conversations whose turn is currently in
flight — dropping an in-flight ``Conversation`` would leave the running
turn writing to a referent the next caller can't find, producing two
parallel writers when the next chat hydrates a fresh copy from disk.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from sdk.context._history import ConversationHistory
from sdk.turn._conversation import Conversation

from ._store import load_conversation_history

logger = logging.getLogger(__name__)

__all__ = ["ConversationCache"]


# Default size — modest, sized for "active conversations in a session"
# rather than "every conversation ever." Disk is authoritative on miss.
_DEFAULT_MAX_SIZE = 25


class ConversationCache:
    """Bounded LRU of ``Conversation`` objects with disk-hydrate on miss.

    Args:
        max_size: Maximum entries before eviction kicks in.
        is_active: Predicate that returns True if the named conversation
            has a turn currently running. The eviction loop skips entries
            for which this is True. Defaults to "never active" — safe but
            allows in-flight turns to be evicted, so callers that run real
            turns should always pass ``sdk.turn.is_turn_active``.
        on_evict: Optional async callback invoked AFTER each eviction with
            the evicted conversation id. Used for channel-specific cleanup
            (e.g. releasing per-conversation browser contexts).
    """

    def __init__(
        self,
        *,
        max_size: int = _DEFAULT_MAX_SIZE,
        is_active: Callable[[str], bool] | None = None,
        on_evict: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._max_size = max_size
        self._is_active = is_active or (lambda _id: False)
        self._on_evict = on_evict
        self._entries: OrderedDict[str, Conversation] = OrderedDict()

    async def get(self, conversation_id: str) -> tuple[Conversation, bool]:
        """Return ``(conversation, is_new)`` for the given id.

        Cache hit: moves to most-recently-used, returns ``is_new=False``.
        Cache miss: hydrates from disk (or creates empty if no history),
        inserts, then triggers eviction of the oldest non-active entries
        if we're over the cap. ``is_new=True`` only when **no on-disk
        history existed** — a genuine first-time use.
        """
        if not conversation_id:
            msg = "conversation_id is required"
            raise ValueError(msg)
        if conversation_id in self._entries:
            self._entries.move_to_end(conversation_id)
            return self._entries[conversation_id], False
        persisted = load_conversation_history(conversation_id)
        is_new = persisted is None
        if is_new:
            logger.info("Creating new conversation %s", conversation_id)
        self._entries[conversation_id] = Conversation(
            id=conversation_id,
            history=ConversationHistory(persisted, instance_id=conversation_id),
        )
        await self._evict_others(exclude=conversation_id)
        return self._entries[conversation_id], is_new

    async def resume(self, conversation_id: str) -> Conversation | None:
        """Force-reload an existing conversation from disk.

        Returns ``None`` if no on-disk history is found. Otherwise replaces
        any cached entry with a fresh one hydrated from disk, marks it
        most-recently-used, and evicts overflow.

        Use this when the caller knows the on-disk state has changed (or
        wants to read it fresh) and the cached copy must not be trusted.
        """
        messages = load_conversation_history(conversation_id)
        if messages is None:
            return None
        self._entries[conversation_id] = Conversation(
            id=conversation_id,
            history=ConversationHistory(messages, instance_id=conversation_id),
        )
        self._entries.move_to_end(conversation_id)
        await self._evict_others(exclude=conversation_id)
        return self._entries[conversation_id]

    def pop(self, conversation_id: str) -> None:
        """Drop the cached entry if present.

        Used after explicit resets (``/new`` in Telegram, picking a
        different conversation) so the next ``get`` rehydrates fresh from
        disk instead of returning a stale in-memory copy.
        """
        self._entries.pop(conversation_id, None)

    def clear(self) -> None:
        """Drop every entry. Used in tests for clean isolation."""
        self._entries.clear()

    def __contains__(self, conversation_id: str) -> bool:
        return conversation_id in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    async def _evict_others(self, *, exclude: str) -> None:
        """Drop the oldest non-active entries until we're at or below cap.

        Conversations whose turn is currently in flight are skipped —
        popping them would leave the running turn writing to a referent
        nobody else can find, and a subsequent chat for the same id would
        rehydrate from disk, producing two parallel writers.

        ``exclude`` skips the conversation that triggered this eviction.
        The caller hasn't yet entered turn_scope for it, so ``is_active``
        cannot recognize it as protected — without this guard the
        just-inserted entry would be evicted by its own insert in the
        rare case where every other cached entry is mid-turn.
        """
        while len(self._entries) > self._max_size:
            for cid in self._entries:
                if cid == exclude:
                    continue
                if not self._is_active(cid):
                    self._entries.pop(cid)
                    if self._on_evict is not None:
                        try:
                            await self._on_evict(cid)
                        except Exception:  # pragma: no cover - defensive
                            logger.exception(
                                "ConversationCache on_evict failed for %s", cid,
                            )
                    logger.info(
                        "Evicted LRU conversation %s from in-memory cache", cid,
                    )
                    break
            else:
                # Every cached conversation is mid-turn (or is the just-
                # inserted caller) — accept temporary overflow rather than
                # evict an active one. The next insert will retry.
                return
