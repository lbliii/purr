"""Full-stack observability — unified event model across the vertical stack.

Aggregates events from:
- **Pounce**: Connection lifecycle (open, request, response, disconnect, close)
- **Bengal/Patitas**: Content pipeline (parse, diff, build effects)
- **Purr**: Reactive pipeline (block updates, SSE broadcasts)

All events are frozen dataclasses with nanosecond timestamps, safe for
concurrent production from multiple worker threads.

Quick Start:
    >>> from purr.observability import StackCollector, EventLog
    >>> log = EventLog()
    >>> collector = StackCollector(log)
    >>> # Pass collector to Pounce as lifecycle_collector
    >>> # Purr pipeline records events via collector.record_reactive(...)

"""

from purr.observability.collector import StackCollector
from purr.observability.events import (
    BlockRecompiled,
    BuildEvent,
    ContentDiffed,
    ContentParsed,
    PipelineProfile,
    ReactiveEvent,
    StackEvent,
    now_ns,
)
from purr.observability.log import EventLog

__all__ = [
    "BlockRecompiled",
    "BuildEvent",
    "ContentDiffed",
    "ContentParsed",
    "EventLog",
    "PipelineProfile",
    "ReactiveEvent",
    "StackCollector",
    "StackEvent",
    "now_ns",
]
