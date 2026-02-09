"""File watcher — triggers the reactive pipeline on content changes.

Monitors content files, templates, data files, and configuration for changes.
When a change is detected, triggers the appropriate pipeline path:

- Content file changed -> re-parse -> AST diff -> reactive update
- Template changed -> recompile -> scope-based refresh
- Config changed -> full dependency cascade

Uses ``watchfiles.awatch`` (async) so the entire watcher lives inside the
event loop — no background threads, no cross-boundary queues, and no
event-loop binding issues on Python 3.14t free-threaded builds.
"""

from __future__ import annotations

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

    Uses ``watchfiles.awatch`` for efficient async filesystem monitoring.
    Categorizes changes by type (content, template, config, asset, route)
    and yields them for consumption by the reactive pipeline.

    Lifecycle is managed entirely via async iteration and task cancellation
    — no background threads or queues required.

    """

    def __init__(self, config: PurrConfig) -> None:
        self._config = config
        self._running = False

    @property
    def is_running(self) -> bool:
        """Whether the async watcher is actively iterating."""
        return self._running

    async def changes(self) -> AsyncIterator[ChangeEvent]:
        """Async iterator that yields ``ChangeEvent`` objects as they occur.

        The iterator runs until the task is cancelled (the expected shutdown
        mechanism).  Cancellation cleanly tears down ``awatch``.

        """
        from watchfiles import awatch

        self._running = True
        try:
            async for raw_changes in awatch(
                self._config.root,
                debounce=300,
                step=100,
            ):
                for change_type, path_str in raw_changes:
                    path = Path(path_str)
                    category = categorize_change(path, self._config)
                    if category is None:
                        continue

                    kind = _CHANGE_KIND_MAP.get(change_type, "modified")
                    yield ChangeEvent(path=path, kind=kind, category=category)
        finally:
            self._running = False
