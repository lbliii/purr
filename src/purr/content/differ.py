"""AST differ — structural diff on Patitas frozen ASTs.

Compares two Patitas Document trees and produces a changeset describing
which nodes were added, removed, or modified. Leverages the fact that
all Patitas AST nodes are frozen dataclasses (hashable, comparable via ==).

The differ uses a known-schema structural diff (not generic tree edit distance)
with fast-path skipping of unchanged subtrees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass

# Patitas AST node types will be imported at implementation time
# from patitas.nodes import Block, Document, Inline, Node, SourceLocation


@dataclass(frozen=True, slots=True)
class ASTChange:
    """A single change between two AST trees.

    Attributes:
        kind: Type of change — added, removed, or modified.
        path: Position in the tree as a tuple of child indices.
        old_node: The node before the change (None for additions).
        new_node: The node after the change (None for removals).

    """

    kind: Literal["added", "removed", "modified"]
    path: tuple[int, ...]
    old_node: object | None
    new_node: object | None


# Phase 2: diff_documents() implementation pending
