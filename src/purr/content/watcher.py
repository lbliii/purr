"""File watcher — triggers the reactive pipeline on content changes.

Monitors content files, templates, data files, and configuration for changes.
When a change is detected, triggers the appropriate pipeline path:

- Content file changed -> re-parse -> AST diff -> reactive update
- Template changed -> recompile -> scope-based refresh
- Config changed -> full dependency cascade
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from watchfiles import Change

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from purr.config import PurrConfig


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    """A file change detected by the watcher.

    Attributes:
        path: Absolute path to the changed file.
        kind: Type of filesystem change.
        category: What kind of file changed (determines pipeline path).

    """

    path: Path
    kind: Literal["created", "modified", "deleted"]
    category: Literal["content", "template", "config", "asset", "route"]


# Mapping from watchfiles Change enum to our kind literals.
_CHANGE_KIND_MAP: dict[Change, Literal["created", "modified", "deleted"]] = {
    Change.added: "created",
    Change.modified: "modified",
    Change.deleted: "deleted",
}


def categorize_change(path: Path, config: PurrConfig) -> str | None:
    """Determine the category of a changed file based on its location.

    Returns None if the file doesn't belong to any watched category.

    """
    try:
        rel = path.relative_to(config.root)
    except ValueError:
        return None

    parts = rel.parts
    if not parts:
        return None

    # Config file at root level
    if len(parts) == 1 and parts[0] in {"purr.yaml", "purr.yml", "purr.toml"}:
        return "config"

    first_dir = parts[0]

    if first_dir == config.content_dir:
        return "content"
    if first_dir == config.templates_dir:
        return "template"
    if first_dir == config.static_dir:
        return "asset"
    if first_dir == config.routes_dir:
        return "route"

    return None


class ContentWatcher:
    """Watches for file changes and triggers reactive updates.

    Uses watchfiles for efficient filesystem monitoring. Categorizes changes
    by type (content, template, config, asset) and routes to the appropriate
    handler in the reactive pipeline.

    The watcher runs watchfiles in a background thread and bridges events
    to an asyncio queue for consumption by the reactive pipeline.

    """

    def __init__(self, config: PurrConfig) -> None:
        self._config = config
        self._queue: asyncio.Queue[ChangeEvent] = asyncio.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        """Whether the watcher background thread is active."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start watching for file changes in a background thread."""
        if self.is_running:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop,
            name="purr-watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the watcher to stop and wait for the thread to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    async def changes(self) -> AsyncIterator[ChangeEvent]:
        """Async iterator that yields ChangeEvent objects as they occur.

        Blocks until a change is available or the watcher is stopped.

        """
        while self.is_running or not self._queue.empty():
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                yield event
            except TimeoutError:
                if not self.is_running:
                    break

    def _watch_loop(self) -> None:
        """Background thread: run watchfiles and push events to the queue."""
        from watchfiles import watch

        watch_path = self._config.root

        for raw_changes in watch(
            watch_path,
            stop_event=self._stop_event,
            debounce=300,
            step=100,
        ):
            for change_type, path_str in raw_changes:
                path = Path(path_str)
                category = categorize_change(path, self._config)
                if category is None:
                    continue

                kind = _CHANGE_KIND_MAP.get(change_type, "modified")
                event = ChangeEvent(path=path, kind=kind, category=category)

                try:
                    self._queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # Drop event if queue is full (unlikely)
