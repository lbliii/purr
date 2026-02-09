"""Tests for purr.reactive.pipeline — reactive pipeline coordinator."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from purr.content.differ import ASTChange
from purr.content.watcher import ChangeEvent
from purr.reactive.broadcaster import Broadcaster
from purr.reactive.graph import DependencyGraph
from purr.reactive.mapper import ReactiveMapper
from purr.reactive.pipeline import (
    ReactivePipeline,
    _CachedContent,
    _compute_edit_region,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def broadcaster() -> Broadcaster:
    return Broadcaster()


@pytest.fixture
def graph() -> DependencyGraph:
    """DependencyGraph with mocked tracer and env."""
    tracer = MagicMock()
    tracer.outputs_needing_rebuild.return_value = set()
    env = MagicMock()
    env.get_template.side_effect = KeyError("not found")
    return DependencyGraph(tracer, env)


@pytest.fixture
def pipeline(broadcaster: Broadcaster, graph: DependencyGraph) -> ReactivePipeline:
    """Pipeline with a mock site containing one page."""
    site = MagicMock()
    page = MagicMock()
    page.source_path = Path("/site/content/page.md")
    page.href = "/page/"
    page.html_content = "<p>Hello</p>"
    page.metadata = {}
    site.pages = [page]

    return ReactivePipeline(
        graph=graph,
        mapper=ReactiveMapper(),
        broadcaster=broadcaster,
        site=site,
    )


# ---------------------------------------------------------------------------
# Tests: _compute_edit_region
# ---------------------------------------------------------------------------


class TestComputeEditRegion:
    """Tests for the edit region computation utility."""

    def test_identical_strings(self) -> None:
        start, end, new_len = _compute_edit_region("hello", "hello")
        assert start == 5
        assert end == 5
        assert new_len == 0

    def test_single_char_replacement(self) -> None:
        start, end, new_len = _compute_edit_region("hello", "hallo")
        assert start == 1
        assert end == 2
        assert new_len == 1

    def test_insertion(self) -> None:
        # "helo" → "hello": the 'l' was inserted at position 3
        # (scanning from both ends, "hel" matches front, "o" matches back)
        start, end, new_len = _compute_edit_region("helo", "hello")
        assert start == 3
        assert end == 3  # zero-length range in old = pure insertion
        assert new_len == 1

    def test_deletion(self) -> None:
        # "hello" → "helo": 'l' at position 3 was deleted
        start, end, new_len = _compute_edit_region("hello", "helo")
        assert start == 3
        assert end == 4
        assert new_len == 0

    def test_append(self) -> None:
        start, end, new_len = _compute_edit_region("abc", "abcdef")
        assert start == 3
        assert end == 3
        assert new_len == 3

    def test_complete_replacement(self) -> None:
        start, end, new_len = _compute_edit_region("abc", "xyz")
        assert start == 0
        assert end == 3
        assert new_len == 3

    def test_empty_to_content(self) -> None:
        start, end, new_len = _compute_edit_region("", "hello")
        assert start == 0
        assert end == 0
        assert new_len == 5


# ---------------------------------------------------------------------------
# Tests: Pipeline content changes
# ---------------------------------------------------------------------------


class TestPipelineContentChange:
    """Tests for handling content changes."""

    @pytest.mark.asyncio
    async def test_content_change_without_cached_ast_is_noop(
        self, pipeline: ReactivePipeline
    ) -> None:
        """First change has no old AST to diff against — does nothing."""
        event = ChangeEvent(
            path=Path("/site/content/page.md"),
            kind="modified",
            category="content",
        )
        # Mock file read and parse
        with (
            patch.object(Path, "read_text", return_value="# Hello\n"),
            patch.object(pipeline, "_parse_content_incremental") as mock_parse,
        ):
            mock_parse.return_value = MagicMock()
            await pipeline.handle_change(event)

        # No old AST, so nothing pushed
        assert pipeline._broadcaster.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_content_change_with_no_structural_diff(
        self, pipeline: ReactivePipeline
    ) -> None:
        """Same AST before and after — no updates pushed."""
        from patitas.location import SourceLocation
        from patitas.nodes import Document, Paragraph, Text

        loc = SourceLocation(lineno=1, col_offset=0)
        doc = Document(
            location=loc,
            children=(Paragraph(location=loc, children=(Text(location=loc, content="Same"),)),),
        )
        path = Path("/site/content/page.md")
        source = "Same\n"

        # Seed the cache
        pipeline._content_cache[path] = _CachedContent(doc=doc, source=source)

        event = ChangeEvent(path=path, kind="modified", category="content")
        with (
            patch.object(Path, "read_text", return_value=source),
            patch.object(
                pipeline, "_parse_content_incremental", return_value=doc
            ),
        ):
            await pipeline.handle_change(event)

        # Same doc -> empty diff -> no updates
        assert pipeline._broadcaster.subscriber_count == 0


class TestPipelineTemplateChange:
    """Tests for handling template changes."""

    @pytest.mark.asyncio
    async def test_template_change_invalidates_cache(
        self, pipeline: ReactivePipeline
    ) -> None:
        """Template change should invalidate block metadata cache."""
        event = ChangeEvent(
            path=Path("/site/templates/page.html"),
            kind="modified",
            category="template",
        )
        # Pre-populate cache
        pipeline._graph._block_meta_cache["page.html"] = {"body": frozenset({"page.body"})}

        await pipeline.handle_change(event)

        # Cache should be invalidated for the changed template
        assert "page.html" not in pipeline._graph._block_meta_cache

    @pytest.mark.asyncio
    async def test_base_template_triggers_cascade_refresh(
        self, pipeline: ReactivePipeline, broadcaster: Broadcaster
    ) -> None:
        """Base template change should push full refresh to all subscribers."""
        from purr.reactive.broadcaster import SSEConnection

        conn = SSEConnection(client_id="c1", permalink="/page/")
        broadcaster.subscribe("/page/", conn)

        event = ChangeEvent(
            path=Path("/site/templates/base.html"),
            kind="modified",
            category="template",
        )
        await pipeline.handle_change(event)

        # Should have pushed a refresh event
        assert not conn.queue.empty()
        item = conn.queue.get_nowait()
        assert item.event == "purr:refresh"


class TestPipelineConfigChange:
    """Tests for handling config changes."""

    @pytest.mark.asyncio
    async def test_config_change_clears_all_caches(
        self, pipeline: ReactivePipeline
    ) -> None:
        pipeline._graph._block_meta_cache["a.html"] = {}
        pipeline._graph._block_meta_cache["b.html"] = {}

        event = ChangeEvent(
            path=Path("/site/purr.yaml"),
            kind="modified",
            category="config",
        )
        await pipeline.handle_change(event)

        assert pipeline._graph._block_meta_cache == {}

    @pytest.mark.asyncio
    async def test_config_change_refreshes_all_subscribers(
        self, pipeline: ReactivePipeline, broadcaster: Broadcaster
    ) -> None:
        from purr.reactive.broadcaster import SSEConnection

        c1 = SSEConnection(client_id="c1", permalink="/a/")
        c2 = SSEConnection(client_id="c2", permalink="/b/")
        broadcaster.subscribe("/a/", c1)
        broadcaster.subscribe("/b/", c2)

        event = ChangeEvent(
            path=Path("/site/purr.yaml"),
            kind="modified",
            category="config",
        )
        await pipeline.handle_change(event)

        assert not c1.queue.empty()
        assert not c2.queue.empty()


class TestPipelineAssetChange:
    """Tests for handling static asset changes."""

    @pytest.mark.asyncio
    async def test_asset_change_refreshes_all_subscribers(
        self, pipeline: ReactivePipeline, broadcaster: Broadcaster
    ) -> None:
        """Asset change should push full refresh to every connected client."""
        from purr.reactive.broadcaster import SSEConnection

        c1 = SSEConnection(client_id="c1", permalink="/a/")
        c2 = SSEConnection(client_id="c2", permalink="/b/")
        broadcaster.subscribe("/a/", c1)
        broadcaster.subscribe("/b/", c2)

        event = ChangeEvent(
            path=Path("/site/static/style.css"),
            kind="modified",
            category="asset",
        )
        await pipeline.handle_change(event)

        assert not c1.queue.empty()
        assert not c2.queue.empty()
        item1 = c1.queue.get_nowait()
        item2 = c2.queue.get_nowait()
        assert item1.event == "purr:refresh"
        assert item2.event == "purr:refresh"

    @pytest.mark.asyncio
    async def test_asset_change_with_no_subscribers(
        self, pipeline: ReactivePipeline
    ) -> None:
        """Asset change with no connected clients is a harmless no-op."""
        event = ChangeEvent(
            path=Path("/site/static/logo.png"),
            kind="created",
            category="asset",
        )
        # Should not raise
        await pipeline.handle_change(event)
        assert pipeline._broadcaster.subscriber_count == 0


class TestSeedASTCache:
    """Tests for seed_ast_cache()."""

    def test_seed_populates_cache(self, pipeline: ReactivePipeline) -> None:
        """seed_ast_cache should parse all content files."""
        pipeline._site.pages[0].source_path = Path("/site/content/page.md")

        with (
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "read_text", return_value="# Hello\n"),
            patch("patitas.parse") as mock_parse,
        ):
            mock_parse.return_value = MagicMock()
            pipeline.seed_ast_cache()

        assert mock_parse.called
        assert Path("/site/content/page.md") in pipeline._content_cache


class TestIncrementalParsing:
    """Tests for the incremental parsing integration."""

    def test_parse_content_incremental_first_time(
        self, pipeline: ReactivePipeline
    ) -> None:
        """First parse (no cache) uses full parse."""
        path = Path("/site/content/page.md")
        source = "# Hello\n"

        with patch("patitas.parse") as mock_full_parse:
            mock_full_parse.return_value = MagicMock()
            result = pipeline._parse_content_incremental(path, source, None)

        mock_full_parse.assert_called_once()
        assert result is not None

    def test_parse_content_incremental_same_source(
        self, pipeline: ReactivePipeline
    ) -> None:
        """Identical source returns cached doc without parsing."""
        from patitas.location import SourceLocation
        from patitas.nodes import Document

        loc = SourceLocation(lineno=1, col_offset=0, offset=0, end_offset=8)
        doc = Document(location=loc, children=())
        source = "# Hello\n"
        cached = _CachedContent(doc=doc, source=source)

        result = pipeline._parse_content_incremental(
            Path("/test.md"), source, cached
        )
        assert result is doc  # Same object — no re-parse

    def test_parse_content_incremental_with_change(
        self, pipeline: ReactivePipeline
    ) -> None:
        """Changed source invokes parse_incremental (not full parse)."""
        from patitas.location import SourceLocation
        from patitas.nodes import Document

        loc = SourceLocation(lineno=1, col_offset=0, offset=0, end_offset=8)
        old_doc = Document(location=loc, children=())
        old_source = "# Hello\n"
        new_source = "# World\n"
        cached = _CachedContent(doc=old_doc, source=old_source)

        # We mock the module-level import inside the method
        mock_mod = MagicMock()
        mock_mod.return_value = MagicMock()

        import importlib
        import sys

        # Temporarily make patitas.incremental available for import
        fake_module = type(sys)("patitas.incremental")
        fake_module.parse_incremental = mock_mod
        sys.modules["patitas.incremental"] = fake_module
        try:
            result = pipeline._parse_content_incremental(
                Path("/test.md"), new_source, cached
            )
        finally:
            sys.modules.pop("patitas.incremental", None)

        mock_mod.assert_called_once()
        assert result is not None
