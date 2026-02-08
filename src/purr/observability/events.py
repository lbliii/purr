"""Unified event model for full-stack observability.

Defines event types for the content pipeline and reactive system.
Pounce lifecycle events are reused directly from ``pounce.lifecycle``.

All events are frozen dataclasses with:
- ``timestamp_ns``: Monotonic nanosecond timestamp
- Descriptive fields for the specific event type

Thread Safety:
    All events are frozen (immutable) and safe to share across threads.

"""

import time
from dataclasses import dataclass
from typing import Literal


# ---------------------------------------------------------------------------
# Content pipeline events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContentParsed:
    """A content file was parsed (full or incremental).

    Attributes:
        path: Absolute path to the content file.
        incremental: True if incremental parsing was used.
        blocks_reused: Number of AST blocks reused from cache.
        blocks_reparsed: Number of AST blocks that were re-parsed.
        parse_ms: Time spent parsing in milliseconds.
        timestamp_ns: Monotonic nanosecond timestamp.

    """

    path: str
    incremental: bool
    blocks_reused: int
    blocks_reparsed: int
    parse_ms: float
    timestamp_ns: int


@dataclass(frozen=True, slots=True)
class ContentDiffed:
    """Two ASTs were diffed, producing a changeset.

    Attributes:
        path: Content file path.
        changes_count: Number of AST changes detected.
        added: Number of added nodes.
        removed: Number of removed nodes.
        modified: Number of modified nodes.
        timestamp_ns: Monotonic nanosecond timestamp.

    """

    path: str
    changes_count: int
    added: int
    removed: int
    modified: int
    timestamp_ns: int


# ---------------------------------------------------------------------------
# Build pipeline events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BuildEvent:
    """A build-pipeline action occurred (Bengal effect).

    Attributes:
        kind: The type of build action.
        source: Source file path (or description).
        target: Output file path (or description).
        duration_ms: Time taken in milliseconds.
        timestamp_ns: Monotonic nanosecond timestamp.

    """

    kind: Literal["render", "copy_asset", "write_index", "generate_sitemap", "custom"]
    source: str
    target: str
    duration_ms: float
    timestamp_ns: int


# ---------------------------------------------------------------------------
# Reactive pipeline events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReactiveEvent:
    """A reactive update was pushed to connected browsers.

    Attributes:
        permalink: Page URL path that was updated.
        blocks_updated: Number of template blocks re-rendered.
        blocks_recompiled: Number of blocks that were selectively recompiled.
        clients_notified: Number of SSE clients that received the update.
        trigger_path: Content file path that triggered the update.
        duration_ms: Time from file change detection to broadcast completion.
        timestamp_ns: Monotonic nanosecond timestamp.

    """

    permalink: str
    blocks_updated: int
    blocks_recompiled: int
    clients_notified: int
    trigger_path: str
    duration_ms: float
    timestamp_ns: int


@dataclass(frozen=True, slots=True)
class BlockRecompiled:
    """A template block was selectively recompiled.

    Attributes:
        template_name: Template file name.
        block_name: Name of the recompiled block.
        reason: Why the block was recompiled.
        timestamp_ns: Monotonic nanosecond timestamp.

    """

    template_name: str
    block_name: str
    reason: Literal["content_change", "template_change", "manual"]
    timestamp_ns: int


# ---------------------------------------------------------------------------
# Union type
# ---------------------------------------------------------------------------

type StackEvent = (
    ContentParsed
    | ContentDiffed
    | BuildEvent
    | ReactiveEvent
    | BlockRecompiled
)


def now_ns() -> int:
    """Return the current monotonic clock value in nanoseconds."""
    return time.monotonic_ns()
