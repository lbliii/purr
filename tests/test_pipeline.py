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
from purr.reactive.pipeline import ReactivePipeline


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
# Tests
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
        # Mock parse to return a document
        with patch.object(pipeline, "_parse_content") as mock_parse:
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

        # Seed the cache
        pipeline._ast_cache[path] = doc

        event = ChangeEvent(path=path, kind="modified", category="content")
        with patch.object(pipeline, "_parse_content", return_value=doc):
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


class TestSeedASTCache:
    """Tests for seed_ast_cache()."""

    def test_seed_populates_cache(self, pipeline: ReactivePipeline) -> None:
        """seed_ast_cache should parse all content files."""
        with patch.object(pipeline, "_parse_content") as mock_parse:
            mock_parse.return_value = MagicMock()
            pipeline._site.pages[0].source_path = Path("/site/content/page.md")

            # Make the path "exist"
            with patch.object(Path, "is_file", return_value=True):
                pipeline.seed_ast_cache()

        assert mock_parse.called
