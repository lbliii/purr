"""Unified dependency graph — combines content and template dependencies.

Merges Bengal's file-level EffectTracer with Kida's block-level dependency
analysis into a single graph that can answer: "this content node changed,
which template blocks are affected?"

This is the bridge between Bengal's "file X changed -> pages Y and Z need
rebuilding" and Kida's "block 'sidebar' depends on page.toc".
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from purr.content.router import _resolve_template_name

if TYPE_CHECKING:
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
        site: Optional Bengal Site for template-to-pages lookup (template changes).

    """

    def __init__(self, tracer: Any, app: Any, *, site: Any = None) -> None:
        self._tracer = tracer
        self._app = app
        self._site = site
        # Cache block metadata per template to avoid repeated analysis
        self._block_meta_cache: dict[str, dict[str, frozenset[str]]] = {}
        # Cache parent -> children map for template inheritance (cascade detection)
        self._extends_map: dict[str, set[str]] | None = None

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

    def pages_using_template(self, template_name: str) -> set[Path]:
        """Return source paths of pages that use the given template.

        Uses site-model-based resolution: iterates site.pages and matches
        by template name (from frontmatter/section). Works in dev mode
        when EffectTracer is empty.

        Args:
            template_name: Template filename (e.g. "page.html", "index.html").

        Returns:
            Set of source file paths for pages using this template.
            Empty set if site is None (graceful degradation).

        """
        if self._site is None:
            return set()
        result: set[Path] = set()
        for page in self._site.pages:
            if not hasattr(page, "source_path") or page.source_path is None:
                continue
            if _resolve_template_name(page) == template_name:
                result.add(Path(page.source_path))
        return result

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

        except Exception:
            # Template not found or analysis failed — return empty deps.
            # The mapper's conservative fallback will handle this by
            # triggering a full page refresh.
            pass

        self._block_meta_cache[template_name] = deps
        return deps

    def invalidate_template_cache(self, template_name: str) -> None:
        """Remove cached block metadata for a template after recompilation."""
        self._block_meta_cache.pop(template_name, None)
        self._extends_map = None

    def invalidate_all_caches(self) -> None:
        """Clear all cached block metadata (e.g., after config change)."""
        self._block_meta_cache.clear()
        self._extends_map = None

    def _build_extends_map(self) -> dict[str, set[str]]:
        """Build parent -> children map from Kida template_metadata().extends."""
        children_of: dict[str, set[str]] = {}
        env = self.kida_env
        if env is None:
            return children_of

        templates: set[str] = set()
        if self._site is not None:
            for page in self._site.pages:
                if hasattr(page, "source_path") and page.source_path is not None:
                    templates.add(_resolve_template_name(page))
        loader = getattr(env, "loader", None)
        if loader is not None and hasattr(loader, "list_templates"):
            try:
                templates.update(loader.list_templates())
            except Exception:
                pass

        for name in templates:
            try:
                template = env.get_template(name)
                meta = template.template_metadata()
                if meta is not None and meta.extends is not None:
                    parent = meta.extends
                    children_of.setdefault(parent, set()).add(name)
            except Exception:
                pass

        return children_of

    def templates_extending(self, template_name: str) -> set[str]:
        """Return template names that extend the given template.

        Used for cascade detection: when a base template changes, all
        templates that extend it need a full refresh.

        """
        if self._extends_map is None:
            self._extends_map = self._build_extends_map()
        return self._extends_map.get(template_name, set()).copy()

    def is_cascade_change(self, event: ChangeEvent) -> bool:
        """Determine if a change triggers a site-wide cascade.

        Config changes and certain template changes (base templates) can
        affect blocks across all pages — headers, navigation, footers.

        Uses Kida's template_metadata().extends when available; falls back
        to a name heuristic when metadata is unavailable.

        """
        if event.category == "config":
            return True

        if event.category == "template":
            template_name = event.path.name
            children = self.templates_extending(template_name)
            if children:
                return True
            # Fallback when Kida metadata unavailable (template not loaded, etc.)
            name = event.path.stem.lower()
            return "base" in name or "layout" in name

        return False
