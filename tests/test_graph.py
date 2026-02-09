"""Tests for purr.reactive.graph — unified dependency graph."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from purr.content.watcher import ChangeEvent
from purr.reactive.graph import DependencyGraph


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _mock_tracer(outputs: set[Path] | None = None) -> MagicMock:
    """Create a mock EffectTracer."""
    tracer = MagicMock()
    tracer.outputs_needing_rebuild.return_value = outputs or set()
    return tracer


def _mock_block_metadata(deps: dict[str, frozenset[str]]) -> MagicMock:
    """Create a mock block_metadata() result.

    Returns a dict of block_name -> mock BlockMetadata with .depends_on.
    """
    metadata = {}
    for name, dep_set in deps.items():
        meta = MagicMock()
        meta.depends_on = dep_set
        metadata[name] = meta
    return metadata


def _mock_kida_env(
    templates: dict[str, dict[str, frozenset[str]]] | None = None,
) -> MagicMock:
    """Create a mock Kida Environment with template.block_metadata()."""
    env = MagicMock()
    templates = templates or {}

    def get_template(name: str) -> MagicMock:
        if name not in templates:
            raise KeyError(name)
        tmpl = MagicMock()
        tmpl.block_metadata.return_value = _mock_block_metadata(templates[name])
        return tmpl

    env.get_template = get_template
    return env


def _mock_app(
    kida_env: MagicMock | None = None,
) -> MagicMock:
    """Create a mock Chirp App with a ``_kida_env`` attribute.

    DependencyGraph resolves the Kida environment lazily from ``app._kida_env``.
    """
    app = MagicMock()
    app._kida_env = kida_env
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAffectedPages:
    """Tests for DependencyGraph.affected_pages()."""

    def test_delegates_to_tracer(self) -> None:
        expected = {Path("content/page.md"), Path("content/other.md")}
        tracer = _mock_tracer(outputs=expected)
        graph = DependencyGraph(tracer, _mock_app(_mock_kida_env()))

        result = graph.affected_pages({Path("content/page.md")})
        assert result == expected
        tracer.outputs_needing_rebuild.assert_called_once()

    def test_empty_change_set(self) -> None:
        tracer = _mock_tracer(outputs=set())
        graph = DependencyGraph(tracer, _mock_app(_mock_kida_env()))

        assert graph.affected_pages(set()) == set()


class TestBlockDepsForTemplate:
    """Tests for DependencyGraph.block_deps_for_template()."""

    def test_returns_block_dependencies(self) -> None:
        env = _mock_kida_env(
            templates={
                "page.html": {
                    "content": frozenset({"content"}),
                    "sidebar": frozenset({"toc"}),
                    "header": frozenset({"site.title", "page.title"}),
                }
            }
        )
        graph = DependencyGraph(_mock_tracer(), _mock_app(env))

        deps = graph.block_deps_for_template("page.html")
        assert deps["content"] == frozenset({"content"})
        assert deps["sidebar"] == frozenset({"toc"})
        assert deps["header"] == frozenset({"site.title", "page.title"})

    def test_missing_template_returns_empty(self) -> None:
        env = _mock_kida_env(templates={})
        graph = DependencyGraph(_mock_tracer(), _mock_app(env))

        assert graph.block_deps_for_template("nonexistent.html") == {}

    def test_results_are_cached(self) -> None:
        env = _mock_kida_env(
            templates={"page.html": {"body": frozenset({"content"})}}
        )
        graph = DependencyGraph(_mock_tracer(), _mock_app(env))

        # First call
        deps1 = graph.block_deps_for_template("page.html")
        # Second call should use cache
        deps2 = graph.block_deps_for_template("page.html")
        assert deps1 is deps2

    def test_invalidate_template_cache(self) -> None:
        env = _mock_kida_env(
            templates={"page.html": {"body": frozenset({"content"})}}
        )
        graph = DependencyGraph(_mock_tracer(), _mock_app(env))

        graph.block_deps_for_template("page.html")
        graph.invalidate_template_cache("page.html")
        assert "page.html" not in graph._block_meta_cache

    def test_invalidate_all_caches(self) -> None:
        env = _mock_kida_env(
            templates={
                "page.html": {"body": frozenset({"content"})},
                "index.html": {"nav": frozenset({"site.pages"})},
            }
        )
        graph = DependencyGraph(_mock_tracer(), _mock_app(env))

        graph.block_deps_for_template("page.html")
        graph.block_deps_for_template("index.html")
        graph.invalidate_all_caches()
        assert graph._block_meta_cache == {}

    def test_kida_env_none_returns_empty_without_caching(self) -> None:
        """When kida_env is None (pre-freeze), return {} but don't cache."""
        graph = DependencyGraph(_mock_tracer(), _mock_app(None))

        deps = graph.block_deps_for_template("page.html")
        assert deps == {}
        # Should NOT be cached so it can be retried after freeze
        assert "page.html" not in graph._block_meta_cache

    def test_kida_env_resolved_lazily(self) -> None:
        """kida_env is read from app._kida_env on each access."""
        app = _mock_app(None)
        graph = DependencyGraph(_mock_tracer(), app)

        assert graph.kida_env is None

        # Simulate freeze making env available
        env = _mock_kida_env(
            templates={"page.html": {"content": frozenset({"content"})}}
        )
        app._kida_env = env

        assert graph.kida_env is env
        deps = graph.block_deps_for_template("page.html")
        assert deps["content"] == frozenset({"content"})


class TestIsCascadeChange:
    """Tests for DependencyGraph.is_cascade_change()."""

    def test_config_change_is_cascade(self) -> None:
        graph = DependencyGraph(_mock_tracer(), _mock_app(_mock_kida_env()))
        event = ChangeEvent(
            path=Path("/site/purr.yaml"), kind="modified", category="config"
        )
        assert graph.is_cascade_change(event) is True

    def test_base_template_is_cascade(self) -> None:
        graph = DependencyGraph(_mock_tracer(), _mock_app(_mock_kida_env()))
        event = ChangeEvent(
            path=Path("/site/templates/base.html"),
            kind="modified",
            category="template",
        )
        assert graph.is_cascade_change(event) is True

    def test_layout_template_is_cascade(self) -> None:
        graph = DependencyGraph(_mock_tracer(), _mock_app(_mock_kida_env()))
        event = ChangeEvent(
            path=Path("/site/templates/layout.html"),
            kind="modified",
            category="template",
        )
        assert graph.is_cascade_change(event) is True

    def test_regular_template_not_cascade(self) -> None:
        graph = DependencyGraph(_mock_tracer(), _mock_app(_mock_kida_env()))
        event = ChangeEvent(
            path=Path("/site/templates/page.html"),
            kind="modified",
            category="template",
        )
        assert graph.is_cascade_change(event) is False

    def test_content_change_not_cascade(self) -> None:
        graph = DependencyGraph(_mock_tracer(), _mock_app(_mock_kida_env()))
        event = ChangeEvent(
            path=Path("/site/content/page.md"),
            kind="modified",
            category="content",
        )
        assert graph.is_cascade_change(event) is False

    def test_asset_change_not_cascade(self) -> None:
        graph = DependencyGraph(_mock_tracer(), _mock_app(_mock_kida_env()))
        event = ChangeEvent(
            path=Path("/site/static/style.css"),
            kind="modified",
            category="asset",
        )
        assert graph.is_cascade_change(event) is False
