"""AST differ — structural diff on Patitas frozen ASTs.

Compares two Patitas Document trees and produces a changeset describing
which nodes were added, removed, or modified. Leverages the fact that
all Patitas AST nodes are frozen dataclasses (hashable, comparable via ==).

The differ uses a known-schema structural diff (not generic tree edit distance)
with fast-path skipping of unchanged subtrees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from patitas.nodes import Block, Document


@dataclass(frozen=True, slots=True)
class ASTChange:
    """A single change between two AST trees.

    Attributes:
        kind: Type of change — added, removed, or modified.
        path: Position in the tree as a tuple of child indices.
            Example: (2, 0) means "third child of root, first child of that".
        old_node: The node before the change (None for additions).
        new_node: The node after the change (None for removals).

    """

    kind: Literal["added", "removed", "modified"]
    path: tuple[int, ...]
    old_node: object | None
    new_node: object | None


def diff_documents(old: Document, new: Document) -> tuple[ASTChange, ...]:
    """Structural diff on two Patitas Document trees.

    Returns a tuple of ASTChange objects describing the differences.
    Unchanged subtrees are skipped in O(1) via ``==`` on frozen nodes.

    Algorithm:
        1. Walk both trees in parallel by child index (positional comparison).
        2. For each position, compare nodes via ``==``.
        3. If equal, skip the subtree (fast path — frozen nodes).
        4. If different types, emit removed + added.
        5. If same type but different content, emit modified.
        6. Handle length mismatches (trailing adds/removes).

    This is NOT a generic tree edit distance (which is NP-hard).
    It's a positional diff on a known schema where children are
    ordered tuples, not arbitrary sets.

    """
    changes: list[ASTChange] = []
    _diff_children(old.children, new.children, (), changes)
    return tuple(changes)


def _diff_children(
    old_children: tuple[Block, ...],
    new_children: tuple[Block, ...],
    parent_path: tuple[int, ...],
    changes: list[ASTChange],
) -> None:
    """Recursively diff ordered child tuples.

    Walks both tuples by index. For positions beyond one tuple's length,
    emits additions or removals as appropriate.

    """
    max_len = max(len(old_children), len(new_children))

    for i in range(max_len):
        path = (*parent_path, i)

        if i >= len(old_children):
            # New node added at end
            changes.append(
                ASTChange(kind="added", path=path, old_node=None, new_node=new_children[i])
            )
        elif i >= len(new_children):
            # Old node removed from end
            changes.append(
                ASTChange(kind="removed", path=path, old_node=old_children[i], new_node=None)
            )
        elif old_children[i] == new_children[i]:
            # Identical subtree — skip (O(1) for frozen nodes)
            continue
        elif type(old_children[i]) is type(new_children[i]):
            # Same type, different content — modified
            changes.append(
                ASTChange(
                    kind="modified", path=path, old_node=old_children[i], new_node=new_children[i]
                )
            )
        else:
            # Different types at same position — remove old, add new
            changes.append(
                ASTChange(kind="removed", path=path, old_node=old_children[i], new_node=None)
            )
            changes.append(
                ASTChange(kind="added", path=path, old_node=None, new_node=new_children[i])
            )
