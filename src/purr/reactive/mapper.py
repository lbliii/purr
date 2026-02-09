"""Reactive mapper — maps content changes to template blocks.

The key innovation in Purr. Given an AST change from the differ and the
template's block metadata from Kida, determines which template blocks
need re-rendering.

Example flow:
    1. Differ reports: Heading node at line 14 was modified
    2. Mapper knows: Heading changes affect ``content`` and ``toc``
    3. Kida reports: block "content" depends on ``content``, ``toc`` (from block_metadata())
    4. Result: re-render the "content" block and push via SSE

Context path names must match the actual template variable names that
Kida's ``DependencyWalker`` detects.  For example, page.html uses
``{{ content | safe }}`` and ``{{ toc | safe }}``, so the mapper must
use ``"content"`` and ``"toc"`` — not ``"page.body"`` or ``"page.toc"``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from purr.content.differ import ASTChange


@dataclass(frozen=True, slots=True)
class BlockUpdate:
    """A template block that needs re-rendering due to a content change.

    Attributes:
        permalink: Page URL path (e.g., "/docs/getting-started/").
        template_name: Kida template file (e.g., "page.html").
        block_name: Block to re-render (e.g., "content", "sidebar").
        context_paths: The context variables that changed, triggering this update.

    """

    permalink: str
    template_name: str
    block_name: str
    context_paths: frozenset[str]


# ---------------------------------------------------------------------------
# Content-to-context mapping
# ---------------------------------------------------------------------------
# Maps Patitas AST node type names to the template context variables they
# affect.  Names must match what Kida's DependencyWalker detects in templates:
#
#   page.html uses:  {{ content | safe }}, {{ toc | safe }}, {{ page.title }},
#                    {{ page.date }}, {{ page.tags }}
#
# The mapping is conservative — it may over-identify affected context paths
# (causing unnecessary re-renders) but never under-identify (causing stale
# content).  When a node type isn't in this map, the FALLBACK covers it.

CONTENT_CONTEXT_MAP: dict[str, frozenset[str]] = {
    "Heading": frozenset({"content", "toc"}),
    "Paragraph": frozenset({"content"}),
    "FencedCode": frozenset({"content"}),
    "IndentedCode": frozenset({"content"}),
    "List": frozenset({"content"}),
    "ListItem": frozenset({"content"}),
    "BlockQuote": frozenset({"content"}),
    "Table": frozenset({"content"}),
    "ThematicBreak": frozenset({"content"}),
    "Directive": frozenset({"content"}),
    "MathBlock": frozenset({"content"}),
    "FootnoteDef": frozenset({"content"}),
    "HtmlBlock": frozenset({"content"}),
}

# Catch-all for unknown node types — conservative
FALLBACK_CONTEXT_PATHS = frozenset({"content", "toc", "page"})


class ReactiveMapper:
    """Maps content AST changes to affected template blocks.

    Uses Kida's block_metadata() to determine which blocks depend on which
    context variables, and ``CONTENT_CONTEXT_MAP`` to connect AST node
    changes to context variable changes.

    The mapping is conservative — it may over-identify affected blocks
    (causing unnecessary re-renders) but never under-identify (causing
    stale content).

    """

    def map_changes(
        self,
        changes: tuple[ASTChange, ...],
        template_name: str,
        block_metadata: dict[str, frozenset[str]],
        permalink: str,
    ) -> tuple[BlockUpdate, ...]:
        """Map AST changes to block updates.

        Args:
            changes: AST changes from the differ.
            template_name: Kida template for this page.
            block_metadata: Per-block context dependencies from Kida.
                Mapping of block name -> frozenset of context paths.
            permalink: URL path of the affected page.

        Returns:
            Tuple of BlockUpdate objects for blocks that need re-rendering.

        """
        if not changes:
            return ()

        # 1. Collect all affected context paths from AST changes
        affected_paths: set[str] = set()
        for change in changes:
            node = change.new_node or change.old_node
            if node is not None:
                node_type = type(node).__name__
                paths = CONTENT_CONTEXT_MAP.get(node_type, FALLBACK_CONTEXT_PATHS)
                affected_paths.update(paths)

        if not affected_paths:
            return ()

        # 2. Find blocks whose dependencies intersect affected paths
        updates: list[BlockUpdate] = []
        for block_name, block_deps in block_metadata.items():
            overlap = block_deps & affected_paths
            if overlap:
                updates.append(
                    BlockUpdate(
                        permalink=permalink,
                        template_name=template_name,
                        block_name=block_name,
                        context_paths=frozenset(overlap),
                    )
                )

        return tuple(updates)
