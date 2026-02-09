"""Stack collector — bridges Pounce lifecycle events into Purr's event log.

Implements Pounce's ``LifecycleCollector`` protocol so it can be passed
directly to Pounce workers.  Also provides methods for recording
build and reactive events from Bengal and Purr.

Thread Safety:
    The collector delegates to ``EventLog`` which is internally locked.
    Safe for concurrent use from multiple Pounce worker threads.

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from purr.observability.events import (
    BlockRecompiled,
    BuildEvent,
    ContentDiffed,
    ContentParsed,
    PipelineProfile,
    ReactiveEvent,
    now_ns,
)
from purr.observability.log import EventLog

if TYPE_CHECKING:
    pass


class StackCollector:
    """Unified event collector for the full stack.

    Implements Pounce's ``LifecycleCollector`` protocol (duck-typed) so
    it can be injected into Pounce workers as the lifecycle collector.
    Also provides explicit methods for recording build and reactive events.

    Args:
        log: The EventLog to store events in.

    """

    __slots__ = ("_log",)

    def __init__(self, log: EventLog | None = None) -> None:
        self._log = log if log is not None else EventLog()

    @property
    def log(self) -> EventLog:
        """The underlying event log."""
        return self._log

    # ----- Pounce LifecycleCollector protocol -----

    def record(self, event: Any) -> None:
        """Record a Pounce lifecycle event.

        Implements the ``LifecycleCollector.record()`` protocol.
        Pounce events are stored directly since they are frozen dataclasses.

        """
        self._log.append(event)

    # ----- Content pipeline events -----

    def record_parse(
        self,
        path: str,
        *,
        incremental: bool = False,
        blocks_reused: int = 0,
        blocks_reparsed: int = 0,
        parse_ms: float = 0.0,
    ) -> None:
        """Record a content parse event."""
        self._log.append(
            ContentParsed(
                path=path,
                incremental=incremental,
                blocks_reused=blocks_reused,
                blocks_reparsed=blocks_reparsed,
                parse_ms=parse_ms,
                timestamp_ns=now_ns(),
            )
        )

    def record_diff(
        self,
        path: str,
        *,
        changes_count: int = 0,
        added: int = 0,
        removed: int = 0,
        modified: int = 0,
    ) -> None:
        """Record an AST diff event."""
        self._log.append(
            ContentDiffed(
                path=path,
                changes_count=changes_count,
                added=added,
                removed=removed,
                modified=modified,
                timestamp_ns=now_ns(),
            )
        )

    # ----- Build events -----

    def record_build(
        self,
        kind: str,
        source: str,
        target: str,
        *,
        duration_ms: float = 0.0,
    ) -> None:
        """Record a build pipeline event."""
        self._log.append(
            BuildEvent(
                kind=kind,  # type: ignore[arg-type]
                source=source,
                target=target,
                duration_ms=duration_ms,
                timestamp_ns=now_ns(),
            )
        )

    # ----- Reactive events -----

    def record_reactive_update(
        self,
        permalink: str,
        *,
        blocks_updated: int = 0,
        blocks_recompiled: int = 0,
        clients_notified: int = 0,
        trigger_path: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        """Record a reactive pipeline update event."""
        self._log.append(
            ReactiveEvent(
                permalink=permalink,
                blocks_updated=blocks_updated,
                blocks_recompiled=blocks_recompiled,
                clients_notified=clients_notified,
                trigger_path=trigger_path,
                duration_ms=duration_ms,
                timestamp_ns=now_ns(),
            )
        )

    def record_block_recompile(
        self,
        template_name: str,
        block_name: str,
        *,
        reason: str = "content_change",
    ) -> None:
        """Record a block recompilation event."""
        self._log.append(
            BlockRecompiled(
                template_name=template_name,
                block_name=block_name,
                reason=reason,  # type: ignore[arg-type]
                timestamp_ns=now_ns(),
            )
        )

    # ----- Pipeline profiling -----

    def record_pipeline_profile(
        self,
        trigger_path: str,
        *,
        blocks_updated: int = 0,
        parse_ms: float = 0.0,
        diff_ms: float = 0.0,
        map_ms: float = 0.0,
        recompile_ms: float = 0.0,
        broadcast_ms: float = 0.0,
        total_ms: float = 0.0,
    ) -> None:
        """Record a pipeline profiling event."""
        self._log.append(
            PipelineProfile(
                trigger_path=trigger_path,
                blocks_updated=blocks_updated,
                parse_ms=parse_ms,
                diff_ms=diff_ms,
                map_ms=map_ms,
                recompile_ms=recompile_ms,
                broadcast_ms=broadcast_ms,
                total_ms=total_ms,
                timestamp_ns=now_ns(),
            )
        )
