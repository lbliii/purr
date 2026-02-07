"""Reactive mapper — maps content changes to template blocks.

The key innovation in Purr. Given an AST change from the differ and the
template's block metadata from Kida, determines which template blocks
need re-rendering.

Example flow:
    1. Differ reports: Heading node at line 14 was modified
    2. Mapper knows: Heading changes affect page.toc (from content model)
    3. Kida reports: block "sidebar" depends on page.toc (from block_metadata())
    4. Result: re-render the "sidebar" block and push via SSE
"""

from __future__ import annotations


class ReactiveMapper:
    """Maps content AST changes to affected template blocks.

    Uses Kida's block_metadata() to determine which blocks depend on which
    context variables, and a content-to-context mapping to connect AST node
    changes to context variable changes.

    The mapping is conservative — it may over-identify affected blocks
    (causing unnecessary re-renders) but never under-identify (causing
    stale content).
    """

    # Phase 2: Implementation pending
