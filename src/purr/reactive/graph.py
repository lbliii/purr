"""Unified dependency graph — combines content and template dependencies.

Merges Bengal's file-level EffectTracer with Kida's block-level dependency
analysis into a single graph that can answer: "this content node changed,
which template blocks are affected?"

This is the bridge between Bengal's "file X changed -> pages Y and Z need
rebuilding" and Kida's "block 'sidebar' depends on page.toc".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from purr.content.watcher import ChangeEvent


class DependencyGraph:
    """Unified dependency graph spanning content, templates, and config.

    Combines:
    - Bengal's EffectTracer (file-level: source -> output dependencies)
    - Kida's BlockMetadata (block-level: block -> context variable dependencies)
    - Content-to-context mapping (AST node type -> template context path)

    Used by the reactive mapper to determine which template blocks need
    re-rendering when a content change is detected.

    The Kida environment is resolved lazily via the Chirp ``app`` reference
    because the environment is not created until the app is frozen (first
    request or ``app.run()``), which happens after the pipeline is set up.

    Args:
        tracer: Bengal's EffectTracer instance for file-level dependency queries.
        app: Chirp App instance.  The Kida environment is read from
            ``app._kida_env`` on first access (after freeze).

    """

    def __init__(self, tracer: Any, app: Any) -> None:
        self._tracer = tracer
        self._app = app
        # Cache block metadata per template to avoid repeated analysis
        self._block_meta_cache: dict[str, dict[str, frozenset[str]]] = {}

    @property
    def kida_env(self) -> Any:
        """The Kida Environment for template introspection and recompilation.

        Resolved lazily from the Chirp app because the environment is
        created during ``_freeze()`` which runs after pipeline setup.

        """
        return getattr(self._app, "_kida_env", None)

    def affected_pages(self, changed_paths: set[Path]) -> set[Path]:
        """Determine which source pages need updating given file changes.

        Delegates to Bengal's EffectTracer for transitive dependency resolution.
        Returns source file paths (not output paths).

        """
        return self._tracer.outputs_needing_rebuild(changed_paths)

    def block_deps_for_template(self, template_name: str) -> dict[str, frozenset[str]]:
        """Get block-level context dependencies for a template.

        Returns a mapping of block name -> frozenset of context paths that
        the block depends on (e.g., ``{"sidebar": frozenset({"page.toc"})}``)

        Delegates to Kida's ``template.block_metadata()`` and extracts the
        ``depends_on`` field from each ``BlockMetadata``.

        Results are cached per template name.

        """
        if template_name in self._block_meta_cache:
            return self._block_meta_cache[template_name]

        deps: dict[str, frozenset[str]] = {}

        try:
            env = self.kida_env
            if env is None:
                # Don't cache — env may become available after freeze.
                return deps
            template = env.get_template(template_name)
            metadata = template.block_metadata()

            for block_name, block_meta in metadata.items():
                # BlockMetadata.depends_on is frozenset[str]
                deps[block_name] = block_meta.depends_on

        except Exception:  # noqa: BLE001
            # Template not found or analysis failed — return empty deps.
            # The mapper's conservative fallback will handle this by
            # triggering a full page refresh.
            pass

        self._block_meta_cache[template_name] = deps
        return deps

    def invalidate_template_cache(self, template_name: str) -> None:
        """Remove cached block metadata for a template after recompilation."""
        self._block_meta_cache.pop(template_name, None)

    def invalidate_all_caches(self) -> None:
        """Clear all cached block metadata (e.g., after config change)."""
        self._block_meta_cache.clear()

    def is_cascade_change(self, event: ChangeEvent) -> bool:
        """Determine if a change triggers a site-wide cascade.

        Config changes and certain template changes (base templates) can
        affect blocks across all pages — headers, navigation, footers.

        """
        if event.category == "config":
            return True

        if event.category == "template":
            # Base templates affect many pages.  A conservative check:
            # if the template name contains "base" or "layout", cascade.
            name = event.path.stem.lower()
            return "base" in name or "layout" in name

        return False
