"""Reactive pipeline coordinator — connects watcher to broadcaster.

Orchestrates the full change propagation flow:
    1. ContentWatcher detects a file change (ChangeEvent)
    2. For content changes: re-parse via Patitas, diff via ASTDiffer
    3. Map AST changes to affected template blocks via ReactiveMapper
    4. Push Fragment updates to browsers via Broadcaster
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from purr.content.differ import diff_documents
from purr.reactive.mapper import ReactiveMapper

if TYPE_CHECKING:
    from patitas.nodes import Document

    from purr.content.watcher import ChangeEvent
    from purr.reactive.broadcaster import Broadcaster
    from purr.reactive.graph import DependencyGraph


class ReactivePipeline:
    """Coordinates change propagation from file edit to browser update.

    Maintains an AST cache for diffing and routes changes through the
    appropriate pipeline path based on the change category.

    Args:
        graph: Unified dependency graph for page and block resolution.
        mapper: Reactive mapper for AST-to-block mapping.
        broadcaster: SSE broadcaster for pushing updates to clients.
        site: Bengal Site for page lookup and context building.

    """

    def __init__(
        self,
        graph: DependencyGraph,
        mapper: ReactiveMapper,
        broadcaster: Broadcaster,
        site: Any,
    ) -> None:
        self._graph = graph
        self._mapper = mapper
        self._broadcaster = broadcaster
        self._site = site
        # AST cache: stores previous Document per content file for diffing.
        # Single-writer (watcher), replace-on-write semantics.
        self._ast_cache: dict[Path, Document] = {}

    async def handle_change(self, event: ChangeEvent) -> None:
        """Process a single file change through the reactive pipeline.

        Routes to the appropriate handler based on the change category.

        """
        if event.category == "content":
            await self._handle_content_change(event)
        elif event.category == "template":
            await self._handle_template_change(event)
        elif event.category == "config":
            await self._handle_config_change(event)
        elif event.category == "route":
            self._handle_route_change(event)
        # asset changes are not propagated (copied via StaticFiles middleware)

    async def _handle_content_change(self, event: ChangeEvent) -> None:
        """Content file changed: re-parse -> diff -> map -> broadcast."""
        from purr.content.router import _resolve_template_name

        path = event.path

        # Re-parse the changed file via Patitas
        new_doc = self._parse_content(path)
        if new_doc is None:
            return

        # Get the old AST for diffing
        old_doc = self._ast_cache.get(path)

        # Update the cache with the new AST
        self._ast_cache[path] = new_doc

        if old_doc is None:
            # No previous AST — can't diff, skip (first load or new file)
            return

        # Diff old vs new
        changes = diff_documents(old_doc, new_doc)
        if not changes:
            return  # No structural changes

        # Find which page(s) this content file belongs to
        for page in self._site.pages:
            if not hasattr(page, "source_path") or page.source_path is None:
                continue
            if Path(page.source_path).resolve() != path.resolve():
                continue

            template_name = _resolve_template_name(page)
            block_metadata = self._graph.block_deps_for_template(template_name)

            permalink = self._get_permalink(page)
            if not permalink:
                continue

            # Map AST changes to block updates
            updates = self._mapper.map_changes(
                changes, template_name, block_metadata, permalink
            )

            if updates:
                # Build updated page context
                context = self._build_page_context(page)
                count = await self._broadcaster.push_updates(updates, context)
                self._log_change(event, len(updates), count)

    async def _handle_template_change(self, event: ChangeEvent) -> None:
        """Template changed: invalidate cache, push full refresh."""
        # Invalidate cached block metadata for the changed template
        template_name = event.path.name
        self._graph.invalidate_template_cache(template_name)

        # If it's a cascade change (base/layout template), refresh all pages
        if self._graph.is_cascade_change(event):
            for permalink in self._broadcaster.get_subscribed_pages():
                await self._broadcaster.push_full_refresh(permalink)
        else:
            # Find affected pages and push refresh for each
            affected = self._graph.affected_pages({event.path})
            for page in self._site.pages:
                if not hasattr(page, "source_path"):
                    continue
                if Path(page.source_path) in affected:
                    permalink = self._get_permalink(page)
                    if permalink:
                        await self._broadcaster.push_full_refresh(permalink)

    async def _handle_config_change(self, event: ChangeEvent) -> None:
        """Config changed: invalidate all caches, push full refresh everywhere."""
        self._graph.invalidate_all_caches()

        for permalink in self._broadcaster.get_subscribed_pages():
            await self._broadcaster.push_full_refresh(permalink)

    def _handle_route_change(self, event: ChangeEvent) -> None:
        """Route file changed: log a restart-required message.

        Dynamic routes are loaded at startup and the Chirp route table
        is frozen after initialization.  Hot-reloading routes would require
        re-freezing the app, which is not supported.

        """
        import sys

        print(
            f"  Route changed: {event.path.name} — restart purr dev to apply",
            file=sys.stderr,
        )

    def _parse_content(self, path: Path) -> Document | None:
        """Parse a content file via Patitas, returning None on error."""
        try:
            from patitas import parse

            source = path.read_text(encoding="utf-8")
            return parse(source, source_file=str(path))
        except Exception as exc:  # noqa: BLE001
            print(f"  Parse error: {path.name}: {exc}", file=sys.stderr)
            return None

    def _build_page_context(self, page: Any) -> dict[str, Any]:
        """Build the Bengal template context for a page."""
        try:
            from bengal.rendering.context import build_page_context

            content = page.html_content or ""
            return build_page_context(page, self._site, content=content, lazy=True)
        except Exception:  # noqa: BLE001
            return {}

    def _get_permalink(self, page: Any) -> str | None:
        """Extract the URL path for a page."""
        if hasattr(page, "href") and page.href:
            return str(page.href)
        if hasattr(page, "_path") and page._path:
            path = str(page._path)
            if not path.startswith("/"):
                path = "/" + path
            return path
        return None

    def _log_change(self, event: ChangeEvent, block_count: int, client_count: int) -> None:
        """Log a reactive update to stderr."""
        name = event.path.name
        blocks = "block" if block_count == 1 else "blocks"
        clients = "client" if client_count == 1 else "clients"
        print(
            f"  {name} changed — {block_count} {blocks} updated, "
            f"{client_count} {clients} notified",
            file=sys.stderr,
        )

    def seed_ast_cache(self) -> None:
        """Pre-parse all content files to populate the AST cache.

        Called at startup so the first edit can be diffed against the
        initial state.

        """
        for page in self._site.pages:
            if not hasattr(page, "source_path") or page.source_path is None:
                continue
            path = Path(page.source_path)
            if path.is_file():
                doc = self._parse_content(path)
                if doc is not None:
                    self._ast_cache[path] = doc
