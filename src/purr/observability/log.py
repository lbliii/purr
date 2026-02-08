"""Event log — queryable, thread-safe event store.

Stores a bounded ring buffer of ``StackEvent`` objects for inspection.
Supports querying by event type, time range, and path.

Thread Safety:
    All methods are protected by a ``threading.Lock``.  Safe for
    concurrent reads and writes from multiple threads.

"""

import threading
from collections import deque
from collections.abc import Sequence
from typing import Any

from purr.observability.events import StackEvent


class EventLog:
    """Bounded event store with query support.

    Events are stored in a ring buffer (deque with maxlen).  When the
    buffer is full, the oldest events are discarded automatically.

    Args:
        max_events: Maximum number of events to retain.

    """

    __slots__ = ("_events", "_lock", "_max_events")

    def __init__(self, max_events: int = 10_000) -> None:
        self._max_events = max_events
        self._events: deque[StackEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()

    def append(self, event: StackEvent) -> None:
        """Record an event in the log."""
        with self._lock:
            self._events.append(event)

    def append_many(self, events: Sequence[StackEvent]) -> None:
        """Record multiple events at once."""
        with self._lock:
            self._events.extend(events)

    def query(
        self,
        *,
        event_type: type | None = None,
        since_ns: int = 0,
        path: str | None = None,
        limit: int = 100,
    ) -> list[StackEvent]:
        """Query events with optional filters.

        Args:
            event_type: Only return events of this type.
            since_ns: Only return events after this timestamp (nanoseconds).
            path: Only return events matching this path (substring match).
            limit: Maximum number of events to return.

        Returns:
            List of matching events, most recent first.

        """
        with self._lock:
            results: list[StackEvent] = []
            # Iterate in reverse (newest first)
            for event in reversed(self._events):
                if len(results) >= limit:
                    break

                if event_type is not None and not isinstance(event, event_type):
                    continue

                ts = getattr(event, "timestamp_ns", 0)
                if since_ns and ts < since_ns:
                    continue

                if path is not None:
                    event_path = getattr(event, "path", None) or getattr(
                        event, "trigger_path", None
                    ) or getattr(event, "source", None) or ""
                    if path not in event_path:
                        continue

                results.append(event)

            return results

    def recent(self, n: int = 20) -> list[StackEvent]:
        """Return the N most recent events."""
        with self._lock:
            items = list(self._events)
        return items[-n:]

    def clear(self) -> int:
        """Clear all events and return the count that was cleared."""
        with self._lock:
            count = len(self._events)
            self._events.clear()
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)

    def stats(self) -> dict[str, Any]:
        """Return summary statistics about stored events."""
        with self._lock:
            events = list(self._events)

        type_counts: dict[str, int] = {}
        for event in events:
            name = type(event).__name__
            type_counts[name] = type_counts.get(name, 0) + 1

        return {
            "total": len(events),
            "max_events": self._max_events,
            "by_type": type_counts,
        }
