"""Tests for purr.reactive.mapper — AST changes to block updates."""

from __future__ import annotations

import pytest

from purr.content.differ import ASTChange
from purr.reactive.mapper import (
    CONTENT_CONTEXT_MAP,
    FALLBACK_CONTEXT_PATHS,
    BlockUpdate,
    ReactiveMapper,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Cache dynamically created node classes by name so type() returns the right name.
_NODE_CLASSES: dict[str, type] = {}


def _make_node(type_name: str) -> object:
    """Create a simple object whose type().__name__ matches *type_name*."""
    if type_name not in _NODE_CLASSES:
        _NODE_CLASSES[type_name] = type(type_name, (), {})
    return _NODE_CLASSES[type_name]()


def _change(kind: str, node_type: str, *, path: tuple[int, ...] = (0,)) -> ASTChange:
    """Create an ASTChange with a node of the given type."""
    node = _make_node(node_type)
    if kind == "added":
        return ASTChange(kind="added", path=path, old_node=None, new_node=node)
    if kind == "removed":
        return ASTChange(kind="removed", path=path, old_node=node, new_node=None)
    return ASTChange(kind="modified", path=path, old_node=node, new_node=node)


# Standard block metadata for testing — mimics a typical page template.
# Context paths must match what Kida's DependencyWalker detects in templates
# (e.g., ``content``, ``toc``, ``page``) — NOT ``page.body``, ``page.toc``.
BLOCK_META: dict[str, frozenset[str]] = {
    "content": frozenset({"content"}),
    "sidebar": frozenset({"toc"}),
    "header": frozenset({"site.title", "page.title"}),
    "footer": frozenset({"site.copyright"}),
}

PERMALINK = "/docs/getting-started/"
TEMPLATE = "page.html"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReactiveMapper:
    """Unit tests for ReactiveMapper.map_changes()."""

    def test_no_changes_returns_empty(self) -> None:
        mapper = ReactiveMapper()
        result = mapper.map_changes((), TEMPLATE, BLOCK_META, PERMALINK)
        assert result == ()

    def test_paragraph_change_hits_content_block(self) -> None:
        mapper = ReactiveMapper()
        changes = (_change("modified", "Paragraph"),)
        result = mapper.map_changes(changes, TEMPLATE, BLOCK_META, PERMALINK)

        assert len(result) == 1
        assert result[0].block_name == "content"
        assert result[0].permalink == PERMALINK
        assert "content" in result[0].context_paths

    def test_heading_change_hits_content_and_sidebar(self) -> None:
        """Heading changes affect ``content`` and ``toc`` context vars."""
        mapper = ReactiveMapper()
        changes = (_change("modified", "Heading"),)
        result = mapper.map_changes(changes, TEMPLATE, BLOCK_META, PERMALINK)

        block_names = {u.block_name for u in result}
        assert "content" in block_names  # depends on "content"
        assert "sidebar" in block_names  # depends on "toc"

    def test_footnote_change_affects_content(self) -> None:
        mapper = ReactiveMapper()
        changes = (_change("added", "FootnoteDef"),)
        result = mapper.map_changes(changes, TEMPLATE, BLOCK_META, PERMALINK)

        block_names = {u.block_name for u in result}
        assert "content" in block_names

    def test_unknown_node_type_uses_fallback(self) -> None:
        """Unknown node types trigger the conservative fallback."""
        mapper = ReactiveMapper()
        changes = (_change("modified", "CustomDirective"),)
        result = mapper.map_changes(changes, TEMPLATE, BLOCK_META, PERMALINK)

        affected_paths: set[str] = set()
        for update in result:
            affected_paths.update(update.context_paths)

        # Fallback includes content, toc, page
        assert affected_paths & FALLBACK_CONTEXT_PATHS

    def test_no_matching_blocks_returns_empty(self) -> None:
        """If no block depends on affected paths, return empty."""
        mapper = ReactiveMapper()
        changes = (_change("modified", "Paragraph"),)
        # Blocks that don't depend on page.body
        block_meta = {"header": frozenset({"site.title"})}
        result = mapper.map_changes(changes, TEMPLATE, block_meta, PERMALINK)

        assert result == ()

    def test_multiple_changes_combine_paths(self) -> None:
        """Multiple changes at different positions combine their context paths."""
        mapper = ReactiveMapper()
        changes = (
            _change("modified", "Paragraph", path=(0,)),
            _change("modified", "Heading", path=(1,)),
        )
        result = mapper.map_changes(changes, TEMPLATE, BLOCK_META, PERMALINK)

        block_names = {u.block_name for u in result}
        assert "content" in block_names
        assert "sidebar" in block_names

    def test_removed_node_uses_old_node_type(self) -> None:
        """For removed nodes, the mapper uses old_node's type."""
        mapper = ReactiveMapper()
        changes = (_change("removed", "Heading"),)
        result = mapper.map_changes(changes, TEMPLATE, BLOCK_META, PERMALINK)

        block_names = {u.block_name for u in result}
        assert "sidebar" in block_names

    def test_block_update_has_correct_template(self) -> None:
        mapper = ReactiveMapper()
        changes = (_change("modified", "Paragraph"),)
        result = mapper.map_changes(changes, TEMPLATE, BLOCK_META, PERMALINK)

        assert all(u.template_name == TEMPLATE for u in result)

    def test_empty_block_metadata_returns_empty(self) -> None:
        mapper = ReactiveMapper()
        changes = (_change("modified", "Paragraph"),)
        result = mapper.map_changes(changes, TEMPLATE, {}, PERMALINK)

        assert result == ()


class TestBlockUpdateDataclass:
    """Verify BlockUpdate is frozen and well-behaved."""

    def test_frozen(self) -> None:
        update = BlockUpdate(
            permalink="/test/",
            template_name="page.html",
            block_name="content",
            context_paths=frozenset({"page.body"}),
        )
        with pytest.raises(AttributeError):
            update.block_name = "other"  # type: ignore[misc]

    def test_hashable(self) -> None:
        a = BlockUpdate(
            permalink="/test/",
            template_name="page.html",
            block_name="content",
            context_paths=frozenset({"page.body"}),
        )
        b = BlockUpdate(
            permalink="/test/",
            template_name="page.html",
            block_name="content",
            context_paths=frozenset({"page.body"}),
        )
        assert a == b
        assert hash(a) == hash(b)


class TestContentContextMap:
    """Verify the CONTENT_CONTEXT_MAP coverage."""

    def test_heading_maps_to_toc_and_content(self) -> None:
        paths = CONTENT_CONTEXT_MAP["Heading"]
        assert "toc" in paths
        assert "content" in paths

    def test_all_block_types_map_to_content(self) -> None:
        """Every known node type should at least affect the ``content`` variable."""
        for node_type, paths in CONTENT_CONTEXT_MAP.items():
            assert "content" in paths, f"{node_type} missing 'content'"

    def test_fallback_is_conservative(self) -> None:
        assert "content" in FALLBACK_CONTEXT_PATHS
        assert "toc" in FALLBACK_CONTEXT_PATHS
        assert "page" in FALLBACK_CONTEXT_PATHS
