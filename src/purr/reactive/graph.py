"""Unified dependency graph — combines content and template dependencies.

Merges Bengal's file-level EffectTracer with Kida's block-level dependency
analysis into a single graph that can answer: "this content node changed,
which template blocks are affected?"

This is the bridge between Bengal's "file X changed → pages Y and Z need
rebuilding" and Kida's "block 'sidebar' depends on page.toc".
"""

from __future__ import annotations


class DependencyGraph:
    """Unified dependency graph spanning content, templates, and config.

    Combines:
    - Bengal's EffectTracer (file-level: source → output dependencies)
    - Kida's BlockMetadata (block-level: block → context variable dependencies)
    - Content-to-context mapping (AST node type → template context path)

    Used by the reactive mapper to determine which template blocks need
    re-rendering when a content change is detected.
    """

    # Phase 2: Implementation pending
