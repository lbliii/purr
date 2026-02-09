"""SSE broadcaster — pushes fragment updates to connected browsers.

Manages SSE connections per page and coordinates fragment delivery.
When the reactive mapper identifies affected blocks, the broadcaster
re-renders them via Kida and pushes the HTML fragments through Chirp's
EventStream to subscribed clients.
"""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from purr.reactive.mapper import BlockUpdate


@dataclass(frozen=True, slots=True)
class SSEConnection:
    """A connected SSE client.

    Attributes:
        client_id: Unique identifier for this connection.
        permalink: The page URL this client is viewing.
        queue: asyncio.Queue[Any] for pushing events to the client's generator.

    """

    client_id: str
    permalink: str
    queue: asyncio.Queue[Any] = field(default_factory=asyncio.Queue, compare=False, hash=False)


class Broadcaster:
    """Manages SSE connections and pushes targeted fragment updates.

    Each connected browser subscribes to updates for the page it's viewing.
    When content changes, the broadcaster:

    1. Receives affected BlockUpdate objects from the ReactiveMapper
    2. Creates Chirp Fragment objects for each block update
    3. Pushes Fragments to subscribers of the affected page via their queues

    Thread-safe: subscriber map protected by a lock.
    Per-worker: each Pounce worker has its own Broadcaster instance.

    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[SSEConnection]] = defaultdict(set)
        self._lock = threading.Lock()

    @property
    def subscriber_count(self) -> int:
        """Total number of active SSE connections across all pages."""
        with self._lock:
            return sum(len(conns) for conns in self._subscribers.values())

    def subscribe(self, permalink: str, conn: SSEConnection) -> None:
        """Register an SSE client for a page."""
        with self._lock:
            self._subscribers[permalink].add(conn)

    def unsubscribe(self, permalink: str, conn: SSEConnection) -> None:
        """Remove an SSE client."""
        with self._lock:
            self._subscribers[permalink].discard(conn)
            if not self._subscribers[permalink]:
                del self._subscribers[permalink]

    def get_subscribers(self, permalink: str) -> frozenset[SSEConnection]:
        """Get all subscribers for a page (snapshot, no lock held on return)."""
        with self._lock:
            return frozenset(self._subscribers.get(permalink, set()))

    def get_subscribed_pages(self) -> frozenset[str]:
        """Get all pages that have at least one subscriber."""
        with self._lock:
            return frozenset(self._subscribers.keys())

    async def push_updates(
        self,
        updates: tuple[BlockUpdate, ...],
        page_context: dict[str, Any],
    ) -> int:
        """Push block updates to subscribers as Chirp Fragment objects.

        Creates a ``chirp.Fragment`` for each BlockUpdate and enqueues it
        on every subscriber's queue for the affected page.

        Args:
            updates: BlockUpdate objects from the ReactiveMapper.
            page_context: The updated template context for rendering.

        Returns:
            Number of fragments pushed (updates x subscribers).

        """
        from chirp import Fragment

        count = 0
        for update in updates:
            subscribers = self.get_subscribers(update.permalink)
            if not subscribers:
                continue

            fragment = Fragment(
                update.template_name,
                update.block_name,
                **page_context,
            )

            for conn in subscribers:
                try:
                    conn.queue.put_nowait(fragment)
                    count += 1
                except asyncio.QueueFull:
                    pass  # Drop if client queue is full

        return count

    async def push_full_refresh(self, permalink: str) -> int:
        """Signal all subscribers for a page to do a full page refresh.

        Sends a special SSE event that the client interprets as a refresh.

        Returns:
            Number of clients notified.

        """
        from chirp import SSEEvent

        subscribers = self.get_subscribers(permalink)
        event = SSEEvent(data="reload", event="purr:refresh")

        count = 0
        for conn in subscribers:
            try:
                conn.queue.put_nowait(event)
                count += 1
            except asyncio.QueueFull:
                pass

        return count

    async def client_generator(self, conn: SSEConnection) -> AsyncIterator[Any]:
        """Async generator that yields events from a connection's queue.

        Used as the generator for Chirp's ``EventStream``. Yields
        Fragment and SSEEvent objects as they arrive on the queue.

        Catches ``CancelledError`` (client disconnect / task cancellation)
        and ``GeneratorExit`` (generator cleanup) to prevent
        ``StopAsyncIteration`` noise from leaking into the event loop's
        exception handler.

        """
        try:
            while True:
                event = await conn.queue.get()
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            return
