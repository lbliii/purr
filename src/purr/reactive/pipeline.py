"""Reactive pipeline coordinator — connects watcher to broadcaster.

Orchestrates the full change propagation flow:
    1. ContentWatcher detects a file change (ChangeEvent)
    2. For content changes: incremental re-parse via Patitas, diff via ASTDiffer
    3. Map AST changes to affected template blocks via ReactiveMapper
    4. Selectively recompile changed Kida template blocks
    5. Push Fragment updates to browsers via Broadcaster

Incremental Pipeline (Move 4):
    When a content file changes, the pipeline now:
    - Computes the edit region by comparing old and new source text
    - Uses ``parse_incremental`` to re-parse only the affected region
    - Uses ``detect_block_changes`` + ``recompile_blocks`` to update
      only the changed template blocks
    - Falls back to full re-parse and full recompile when needed
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from purr.content.differ import diff_documents
from purr.reactive.mapper import ReactiveMapper

if TYPE_CHECKING:
    from patitas.nodes import Document

    from purr.content.watcher import ChangeEvent
    from purr.observability.collector import StackCollector
    from purr.observability.profiler import PipelineProfiler
    from purr.reactive.broadcaster import Broadcaster
    from purr.reactive.graph import DependencyGraph


@dataclass(slots=True)
class _CachedContent:
    """Cached content state: AST + source text for incremental parsing."""

    doc: Document
    source: str


def _strip_frontmatter(source: str) -> str:
    """Strip YAML frontmatter from markdown source, returning the body.

    Frontmatter is delimited by ``---`` on its own line at the start of the file.
    If no valid frontmatter is found, returns the full source unchanged.

    """
    if not source.startswith("---"):
        return source
    end = source.find("\n---", 3)
    if end == -1:
        return source
    # Skip past the closing "---" and strip leading blank lines
    return source[end + 4:].lstrip("\n")


def _compute_edit_region(old: str, new: str) -> tuple[int, int, int]:
    """Compute the minimal edit region between old and new source.

    Returns (edit_start, edit_end, new_length):
        - edit_start: first byte that differs (offset in old)
        - edit_end: end of differing region in old
        - new_length: length of replacement text in new

    Scans from both ends to find the minimal changed region.

    """
    # Find first difference from the start
    min_len = min(len(old), len(new))
    start = 0
    while start < min_len and old[start] == new[start]:
        start += 1

    if start == len(old) == len(new):
        # No differences
        return start, start, 0

    # Find first difference from the end
    old_end = len(old) - 1
    new_end = len(new) - 1
    while old_end >= start and new_end >= start and old[old_end] == new[new_end]:
        old_end -= 1
        new_end -= 1

    edit_start = start
    edit_end = old_end + 1  # exclusive
    new_length = new_end - start + 1

    return edit_start, edit_end, new_length


class ReactivePipeline:
    """Coordinates change propagation from file edit to browser update.

    Maintains an AST + source cache for incremental diffing and routes
    changes through the appropriate pipeline path.

    The incremental pipeline (Move 4) replaces full re-parsing with:
    - Patitas ``parse_incremental`` for O(change) AST updates
    - Kida ``recompile_blocks`` for O(changed_blocks) template updates

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
        collector: StackCollector | None = None,
    ) -> None:
        self._graph = graph
        self._mapper = mapper
        self._broadcaster = broadcaster
        self._site = site
        self._collector = collector
        self._profiler: PipelineProfiler | None = None
        # Content cache: stores previous AST + source per file for incremental parsing.
        # Single-writer (watcher), replace-on-write semantics.
        self._content_cache: dict[Path, _CachedContent] = {}

        # Markdown renderer for re-rendering content on changes.
        # Must match the config used in app._parse_pages() at startup.
        from patitas import Markdown

        self._md_renderer = Markdown(plugins=["table"])

        # Create profiler if collector is available
        if collector is not None:
            from purr.observability.profiler import PipelineProfiler

            self._profiler = PipelineProfiler(collector.log)

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
        elif event.category == "asset":
            await self._handle_asset_change(event)

    async def _handle_content_change(self, event: ChangeEvent) -> None:
        """Content file changed: incremental parse -> diff -> map -> recompile -> broadcast."""
        try:
            await self._handle_content_change_inner(event)
        except Exception as exc:
            await self._broadcast_error(exc, event)

    async def _handle_content_change_inner(self, event: ChangeEvent) -> None:
        """Inner content change handler (unwrapped for error overlay)."""
        from purr.content.router import _resolve_template_name

        path = event.path
        profiler = self._profiler

        if profiler is not None:
            profiler.begin(str(path))

        # Read new source
        try:
            new_source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"  Read error: {path.name}: {exc}", file=sys.stderr)
            return

        # Get cached state for incremental parsing
        cached = self._content_cache.get(path)

        # Incremental or full parse
        if profiler is not None:
            profiler.start("parse")
        new_doc = self._parse_content_incremental(path, new_source, cached)
        if profiler is not None:
            profiler.stop("parse")
        if new_doc is None:
            return

        # Extract old doc for diffing
        old_doc = cached.doc if cached is not None else None

        # Update the cache with new state
        self._content_cache[path] = _CachedContent(doc=new_doc, source=new_source)

        # Re-render HTML so full page loads serve fresh content.
        # The route handler reads page.html_content on every request;
        # without this, only SSE fragment updates would reflect changes.
        self._update_page_html(path, new_source)

        if old_doc is None:
            # No previous AST — can't diff, skip (first load or new file)
            return

        # Diff old vs new
        if profiler is not None:
            profiler.start("diff")
        changes = diff_documents(old_doc, new_doc)
        if profiler is not None:
            profiler.stop("diff")
        if not changes:
            return  # No structural changes

        if self._collector is not None:
            added = sum(1 for c in changes if c.kind == "added")
            removed = sum(1 for c in changes if c.kind == "removed")
            modified = sum(1 for c in changes if c.kind == "modified")
            self._collector.record_diff(
                str(path), changes_count=len(changes),
                added=added, removed=removed, modified=modified,
            )

        # Find which page(s) this content file belongs to
        total_blocks_updated = 0
        affected_permalinks: list[str] = []
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

            affected_permalinks.append(permalink)

            # Attempt selective block recompilation
            if profiler is not None:
                profiler.start("recompile")
            t_recompile = time.perf_counter()
            blocks_recompiled = self._try_recompile_blocks(template_name)
            if profiler is not None:
                profiler.stop("recompile")

            # Map AST changes to block updates
            if profiler is not None:
                profiler.start("map")
            updates = self._mapper.map_changes(
                changes, template_name, block_metadata, permalink
            )
            if profiler is not None:
                profiler.stop("map")

            if updates:
                # Build updated page context
                if profiler is not None:
                    profiler.start("broadcast")
                context = self._build_page_context(page)
                count = await self._broadcaster.push_updates(updates, context)
                if profiler is not None:
                    profiler.stop("broadcast")
                duration_ms = (time.perf_counter() - t_recompile) * 1000
                total_blocks_updated += len(updates)

                if self._collector is not None:
                    self._collector.record_reactive_update(
                        permalink,
                        blocks_updated=len(updates),
                        blocks_recompiled=blocks_recompiled,
                        clients_notified=count,
                        trigger_path=str(path),
                        duration_ms=duration_ms,
                    )

        # Fallback: if the targeted fragment path produced zero block updates
        # (e.g. block_metadata unavailable, mapper couldn't resolve deps),
        # push a full page refresh so the browser still gets notified.
        if total_blocks_updated == 0 and affected_permalinks:
            for permalink in affected_permalinks:
                await self._broadcaster.push_full_refresh(permalink)

        # Emit the profiling event (replaces the old _log_change call)
        if profiler is not None and total_blocks_updated > 0:
            profiler.finish(blocks_updated=total_blocks_updated)

    async def _handle_template_change(self, event: ChangeEvent) -> None:
        """Template changed: invalidate cache, push full refresh."""
        try:
            await self._handle_template_change_inner(event)
        except Exception as exc:
            await self._broadcast_error(exc, event)

    async def _handle_template_change_inner(self, event: ChangeEvent) -> None:
        """Inner template change handler (unwrapped for error overlay)."""
        # Invalidate cached block metadata for the changed template
        template_name = event.path.name
        self._graph.invalidate_template_cache(template_name)

        # If it's a cascade change (base/layout template), refresh all pages
        if self._graph.is_cascade_change(event):
            for permalink in self._broadcaster.get_subscribed_pages():
                await self._broadcaster.push_full_refresh(permalink)
        else:
            # Find affected pages via site-model (template name -> source paths)
            affected_source_paths = self._graph.pages_using_template(template_name)
            for page in self._site.pages:
                if hasattr(page, "source_path") and Path(page.source_path) in affected_source_paths:
                    permalink = self._get_permalink(page)
                    if permalink:
                        await self._broadcaster.push_full_refresh(permalink)

    async def _broadcast_error(self, exc: BaseException, event: ChangeEvent) -> None:
        """Broadcast an error to all connected clients via SSE."""
        from purr.reactive.error_overlay import format_error_event

        print(
            f"  Pipeline error ({event.path.name}): {exc}",
            file=sys.stderr,
        )

        payload = format_error_event(exc)
        for permalink in self._broadcaster.get_subscribed_pages():
            subscribers = self._broadcaster.get_subscribers(permalink)
            for conn in subscribers:
                try:
                    from chirp.http.response import SSEEvent

                    await conn.queue.put(SSEEvent(data=payload, event="purr:error"))
                except Exception:
                    pass

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

    async def _handle_asset_change(self, event: ChangeEvent) -> None:
        """Static asset changed: push full refresh to all connected clients.

        Static files are served directly from disk via StaticFiles middleware,
        so the new content is already available — the browser just needs to
        know to re-request it.

        """
        print(
            f"  Asset changed: {event.path.name}",
            file=sys.stderr,
        )

        for permalink in self._broadcaster.get_subscribed_pages():
            await self._broadcaster.push_full_refresh(permalink)

    def _parse_content_incremental(
        self,
        path: Path,
        new_source: str,
        cached: _CachedContent | None,
    ) -> Document | None:
        """Parse content, using incremental parsing when possible.

        Falls back to full parse when:
        - No cached state exists (first load)
        - Edit region computation fails
        - Incremental parse itself falls back internally

        """
        try:
            from patitas import parse

            t0 = time.perf_counter()

            if cached is None:
                # First parse — no previous AST to diff against
                doc = parse(new_source, source_file=str(path))
                ms = (time.perf_counter() - t0) * 1000
                if self._collector is not None:
                    self._collector.record_parse(
                        str(path), incremental=False,
                        blocks_reparsed=len(doc.children) if doc else 0,
                        parse_ms=ms,
                    )
                return doc

            if cached.source == new_source:
                return cached.doc  # No change

            # Compute edit region
            edit_start, edit_end, new_length = _compute_edit_region(
                cached.source, new_source
            )

            # Use incremental parsing
            from patitas.incremental import parse_incremental

            doc = parse_incremental(
                new_source,
                cached.doc,
                edit_start,
                edit_end,
                new_length,
                source_file=str(path),
            )
            ms = (time.perf_counter() - t0) * 1000

            if self._collector is not None:
                total_blocks = len(doc.children) if doc else 0
                old_blocks = len(cached.doc.children)
                reused = max(0, total_blocks - (total_blocks - old_blocks + 1))
                self._collector.record_parse(
                    str(path), incremental=True,
                    blocks_reused=reused,
                    blocks_reparsed=max(1, total_blocks - reused),
                    parse_ms=ms,
                )
            return doc
        except Exception as exc:
            print(f"  Parse error: {path.name}: {exc}", file=sys.stderr)
            return None

    def _try_recompile_blocks(self, template_name: str) -> int:
        """Attempt selective block recompilation for a template.

        Uses Kida's block_recompile module to detect which template blocks
        changed and recompile only those, patching the live Template object.

        This is a best-effort optimization — failures are silently ignored
        and the template will be fully recompiled on next access if needed.

        Returns:
            Number of blocks recompiled (0 if none or on failure).

        """
        try:
            from kida.compiler.block_recompile import (
                detect_block_changes,
                recompile_blocks,
            )

            # Get the Kida environment and compiled template
            kida_env = self._graph.kida_env
            if kida_env is None:
                return 0

            template = kida_env._cache.get(template_name)
            if template is None:
                return 0  # Not cached; will be compiled on next access

            # Need old and new AST for block comparison
            old_ast = getattr(template, "_optimized_ast", None)
            if old_ast is None:
                return 0  # No AST preserved; can't compare

            # Recompile the template to get the new AST
            try:
                source, filename = kida_env.loader.get_source(template_name)
            except Exception:
                return 0

            from kida.lexer import Lexer
            from kida.parser import Parser

            lexer = Lexer(source, kida_env._lexer_config)
            tokens = list(lexer.tokenize())
            should_escape = (
                kida_env.autoescape(template_name)
                if callable(kida_env.autoescape)
                else kida_env.autoescape
            )
            parser = Parser(tokens, template_name, filename, source, autoescape=should_escape)
            new_ast = parser.parse()

            # Detect block-level changes
            delta = detect_block_changes(old_ast, new_ast)
            if not delta.has_changes:
                return 0  # No block changes

            # Recompile only the changed blocks
            recompiled = recompile_blocks(kida_env, template, new_ast, delta)
            if recompiled:
                print(
                    f"  Recompiled {len(recompiled)} block(s): {', '.join(sorted(recompiled))}",
                    file=sys.stderr,
                )

                # Record individual block recompile events
                if self._collector is not None:
                    for block_name in recompiled:
                        self._collector.record_block_recompile(
                            template_name, block_name, reason="content_change",
                        )

            return len(recompiled)

        except Exception:
            return 0  # Best-effort; full recompile on next access

    def _update_page_html(self, path: Path, source: str) -> None:
        """Re-render markdown to HTML and update the page object.

        Ensures full page loads serve fresh content, not just SSE fragment
        updates.  Strips frontmatter, re-renders the body via Patitas, and
        writes back to ``page.html_content`` and ``page._raw_content``.

        """
        body = _strip_frontmatter(source)
        for page in self._site.pages:
            if not hasattr(page, "source_path") or page.source_path is None:
                continue
            if Path(page.source_path).resolve() != path.resolve():
                continue
            page.html_content = self._md_renderer(body)
            page._raw_content = body
            break

    def _build_page_context(self, page: Any) -> dict[str, Any]:
        """Build the Bengal template context for a page."""
        try:
            from bengal.rendering.context import build_page_context

            content = page.html_content or ""
            return build_page_context(page, self._site, content=content, lazy=True)
        except Exception:
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
        """Pre-parse all content files to populate the content cache.

        Called at startup so the first edit can be diffed against the
        initial state.  Stores both the AST and source text for
        incremental parsing.

        """
        from patitas import parse

        for page in self._site.pages:
            if not hasattr(page, "source_path") or page.source_path is None:
                continue
            path = Path(page.source_path)
            if path.is_file():
                try:
                    source = path.read_text(encoding="utf-8")
                    doc = parse(source, source_file=str(path))
                    self._content_cache[path] = _CachedContent(doc=doc, source=source)
                except Exception as exc:
                    print(f"  Cache seed error: {path.name}: {exc}", file=sys.stderr)
