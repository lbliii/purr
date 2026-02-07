"""Tests for purr.content.differ — AST structural diffing."""

from __future__ import annotations

from patitas.location import SourceLocation
from patitas.nodes import (
    Document,
    FencedCode,
    Heading,
    Paragraph,
    Text,
    ThematicBreak,
)

from purr.content.differ import ASTChange, diff_documents

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOC = SourceLocation(lineno=1, col_offset=0)


def _doc(*children) -> Document:
    """Create a Document with the given block children."""
    return Document(location=_LOC, children=tuple(children))


def _heading(level: int, text: str) -> Heading:
    return Heading(
        location=_LOC,
        level=level,
        children=(Text(location=_LOC, content=text),),
    )


def _paragraph(text: str) -> Paragraph:
    return Paragraph(
        location=_LOC,
        children=(Text(location=_LOC, content=text),),
    )


def _code(info: str, content: str) -> FencedCode:
    return FencedCode(
        location=_LOC,
        source_start=0,
        source_end=len(content),
        info=info,
        content_override=content,
    )


def _hr() -> ThematicBreak:
    return ThematicBreak(location=_LOC)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDiffDocuments:
    """Unit tests for diff_documents()."""

    def test_identical_documents_produce_no_changes(self) -> None:
        doc = _doc(_heading(1, "Hello"), _paragraph("World"))
        assert diff_documents(doc, doc) == ()

    def test_identical_content_different_objects(self) -> None:
        """Frozen dataclass equality means structurally equal trees match."""
        old = _doc(_paragraph("Same content"))
        new = _doc(_paragraph("Same content"))
        assert diff_documents(old, new) == ()

    def test_empty_documents(self) -> None:
        assert diff_documents(_doc(), _doc()) == ()

    def test_added_node_at_end(self) -> None:
        old = _doc(_heading(1, "Title"))
        new = _doc(_heading(1, "Title"), _paragraph("New paragraph"))
        changes = diff_documents(old, new)

        assert len(changes) == 1
        assert changes[0].kind == "added"
        assert changes[0].path == (1,)
        assert changes[0].old_node is None
        assert isinstance(changes[0].new_node, Paragraph)

    def test_removed_node_from_end(self) -> None:
        old = _doc(_heading(1, "Title"), _paragraph("Gone"))
        new = _doc(_heading(1, "Title"))
        changes = diff_documents(old, new)

        assert len(changes) == 1
        assert changes[0].kind == "removed"
        assert changes[0].path == (1,)
        assert isinstance(changes[0].old_node, Paragraph)
        assert changes[0].new_node is None

    def test_modified_same_type(self) -> None:
        """Same node type at same position with different content -> modified."""
        old = _doc(_paragraph("Before"))
        new = _doc(_paragraph("After"))
        changes = diff_documents(old, new)

        assert len(changes) == 1
        assert changes[0].kind == "modified"
        assert changes[0].path == (0,)
        assert isinstance(changes[0].old_node, Paragraph)
        assert isinstance(changes[0].new_node, Paragraph)

    def test_type_change_produces_remove_and_add(self) -> None:
        """Different node types at same position -> removed + added."""
        old = _doc(_paragraph("Text"))
        new = _doc(_heading(2, "Now a heading"))
        changes = diff_documents(old, new)

        assert len(changes) == 2
        assert changes[0].kind == "removed"
        assert changes[0].path == (0,)
        assert isinstance(changes[0].old_node, Paragraph)
        assert changes[1].kind == "added"
        assert changes[1].path == (0,)
        assert isinstance(changes[1].new_node, Heading)

    def test_multiple_changes(self) -> None:
        """Several changes across the document."""
        old = _doc(
            _heading(1, "Title"),
            _paragraph("First"),
            _paragraph("Second"),
        )
        new = _doc(
            _heading(1, "Title"),       # unchanged
            _paragraph("Modified"),     # modified
            _paragraph("Second"),       # unchanged
            _paragraph("Added"),        # added
        )
        changes = diff_documents(old, new)

        assert len(changes) == 2
        # Position 1 modified
        assert changes[0].kind == "modified"
        assert changes[0].path == (1,)
        # Position 3 added
        assert changes[1].kind == "added"
        assert changes[1].path == (3,)

    def test_heading_level_change_is_modified(self) -> None:
        """Changing heading level keeps the type but modifies the node."""
        old = _doc(_heading(1, "Title"))
        new = _doc(_heading(2, "Title"))
        changes = diff_documents(old, new)

        assert len(changes) == 1
        assert changes[0].kind == "modified"

    def test_code_block_change(self) -> None:
        old = _doc(_code("python", "print('hello')"))
        new = _doc(_code("python", "print('world')"))
        changes = diff_documents(old, new)

        assert len(changes) == 1
        assert changes[0].kind == "modified"
        assert isinstance(changes[0].old_node, FencedCode)

    def test_all_nodes_removed(self) -> None:
        old = _doc(_heading(1, "A"), _paragraph("B"), _paragraph("C"))
        new = _doc()
        changes = diff_documents(old, new)

        assert len(changes) == 3
        assert all(c.kind == "removed" for c in changes)
        assert [c.path for c in changes] == [(0,), (1,), (2,)]

    def test_all_nodes_added(self) -> None:
        old = _doc()
        new = _doc(_heading(1, "A"), _paragraph("B"))
        changes = diff_documents(old, new)

        assert len(changes) == 2
        assert all(c.kind == "added" for c in changes)

    def test_thematic_break_to_paragraph(self) -> None:
        """Type change: ThematicBreak -> Paragraph."""
        old = _doc(_hr())
        new = _doc(_paragraph("Replaced"))
        changes = diff_documents(old, new)

        assert len(changes) == 2
        assert changes[0].kind == "removed"
        assert isinstance(changes[0].old_node, ThematicBreak)
        assert changes[1].kind == "added"
        assert isinstance(changes[1].new_node, Paragraph)


class TestASTChangeDataclass:
    """Verify ASTChange is frozen and well-behaved."""

    def test_frozen(self) -> None:
        change = ASTChange(kind="added", path=(0,), old_node=None, new_node=None)
        import pytest

        with pytest.raises(AttributeError):
            change.kind = "removed"  # type: ignore[misc]

    def test_hashable(self) -> None:
        a = ASTChange(kind="added", path=(0,), old_node=None, new_node="x")
        b = ASTChange(kind="added", path=(0,), old_node=None, new_node="x")
        assert a == b
        assert hash(a) == hash(b)
        assert len({a, b}) == 1
