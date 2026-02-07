"""File watcher — triggers the reactive pipeline on content changes.

Monitors content files, templates, data files, and configuration for changes.
When a change is detected, triggers the appropriate pipeline path:

- Content file changed → re-parse → AST diff → reactive update
- Template changed → recompile → scope-based refresh
- Config changed → full dependency cascade
"""

from __future__ import annotations


class ContentWatcher:
    """Watches for file changes and triggers reactive updates.

    Uses watchfiles for efficient filesystem monitoring. Categorizes changes
    by type (content, template, config, asset) and routes to the appropriate
    handler in the reactive pipeline.
    """

    # Phase 2: Implementation pending
