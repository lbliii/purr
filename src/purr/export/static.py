"""Static export — pre-render the live app to HTML files.

Renders all routes (static content + dynamic Chirp routes) to plain HTML
files suitable for deployment to any static hosting service.

For content pages, this is equivalent to Bengal's existing build pipeline.
For dynamic routes, it pre-renders with default state (empty query params,
no session, etc.).
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from purr._errors import ExportError

if TYPE_CHECKING:
    from bengal.core.site import Site
    from chirp import App

    from purr.config import PurrConfig
    from purr.routes.loader import RouteDefinition


@dataclass(frozen=True, slots=True)
class ExportedFile:
    """Record of a single file written during export.

    Attributes:
        source_path: Logical source (e.g., ``"/docs/getting-started/"``).
        output_path: Absolute filesystem path to the written file.
        source_type: Category of the exported file.
        size_bytes: Size of the written file in bytes.
        duration_ms: Time taken to render and write this file.

    """

    source_path: str
    output_path: Path
    source_type: Literal["content", "dynamic", "asset", "sitemap", "error_page"]
    size_bytes: int
    duration_ms: float


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Aggregate result of a full static export.

    Attributes:
        files: All files written during export.
        total_pages: Number of content + dynamic pages exported.
        total_assets: Number of static asset files copied.
        duration_ms: Total wall-clock time for the export.
        output_dir: Absolute path to the output directory.

    """

    files: tuple[ExportedFile, ...]
    total_pages: int
    total_assets: int
    duration_ms: float
    output_dir: Path


class StaticExporter:
    """Exports a Purr application as static files.

    Iterates all registered routes (content + dynamic), renders each to HTML,
    and writes the output to the configured directory structure.

    Also handles:
    - Static asset copying with optional fingerprinting
    - Sitemap generation
    - 404 page rendering

    Args:
        site: Bengal Site containing content pages.
        app: Chirp App with compiled Kida template environment.
        config: Frozen Purr configuration.
        routes: Dynamic route definitions (may be empty).

    """

    def __init__(
        self,
        site: Site,
        app: App,
        config: PurrConfig,
        routes: tuple[RouteDefinition, ...] = (),
    ) -> None:
        self._site = site
        self._app = app
        self._config = config
        self._routes = routes

    def export(self) -> ExportResult:
        """Run the full export pipeline and return the result.

        Pipeline order:
            1. Clean output directory
            2. Render content pages
            3. Pre-render dynamic routes (GET only)
            4. Copy static assets
            5. Render 404 page (if template exists)
            6. Generate sitemap (if base_url configured)
            7. Fingerprint assets and rewrite references (if enabled)

        Returns:
            ExportResult with metadata about all exported files.

        Raises:
            ExportError: If any step of the pipeline fails.

        """
        start = time.perf_counter()
        output_dir = self._config.output_path

        # 1. Clean output directory
        self._clean_output(output_dir)

        all_files: list[ExportedFile] = []

        # 2. Render content pages
        content_files = self._render_content_pages(output_dir)
        all_files.extend(content_files)

        # 3. Pre-render dynamic routes
        dynamic_files = self._render_dynamic_routes(output_dir)
        all_files.extend(dynamic_files)

        # 4. Copy static assets
        asset_files = self._copy_assets(output_dir)
        all_files.extend(asset_files)

        # 5. Render 404 page
        error_files = self._render_error_pages(output_dir)
        all_files.extend(error_files)

        # 6. Generate sitemap
        sitemap_files = self._generate_sitemap(output_dir, all_files)
        all_files.extend(sitemap_files)

        # 7. Asset fingerprinting (rewrites HTML in-place)
        if getattr(self._config, "fingerprint", False):
            self._fingerprint_assets(output_dir)

        elapsed = (time.perf_counter() - start) * 1000

        total_pages = sum(
            1
            for f in all_files
            if f.source_type in ("content", "dynamic")
        )
        total_assets = sum(1 for f in all_files if f.source_type == "asset")

        return ExportResult(
            files=tuple(all_files),
            total_pages=total_pages,
            total_assets=total_assets,
            duration_ms=elapsed,
            output_dir=output_dir,
        )

    # ------------------------------------------------------------------
    # Pipeline steps (implemented in subsequent tasks)
    # ------------------------------------------------------------------

    def _clean_output(self, output_dir: Path) -> None:
        """Remove and recreate the output directory."""
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    def _render_content_pages(self, output_dir: Path) -> list[ExportedFile]:
        """Render all Bengal content pages to HTML files."""
        # Task 2: implementation
        return []

    def _render_dynamic_routes(self, output_dir: Path) -> list[ExportedFile]:
        """Pre-render dynamic Chirp routes with default state."""
        # Task 5: implementation
        return []

    def _copy_assets(self, output_dir: Path) -> list[ExportedFile]:
        """Copy static assets to the output directory."""
        # Task 3: implementation
        return []

    def _render_error_pages(self, output_dir: Path) -> list[ExportedFile]:
        """Render error pages (404, etc.) if templates exist."""
        # Task 8: implementation
        return []

    def _generate_sitemap(
        self,
        output_dir: Path,
        exported: list[ExportedFile],
    ) -> list[ExportedFile]:
        """Generate sitemap.xml from exported pages."""
        # Task 7: implementation
        return []

    def _fingerprint_assets(self, output_dir: Path) -> None:
        """Hash asset filenames and rewrite HTML references."""
        # Task 6: implementation

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _permalink_to_filepath(permalink: str, output_dir: Path) -> Path:
        """Convert a URL permalink to an output file path.

        Clean URL convention:
            ``/``                  -> ``output/index.html``
            ``/about/``           -> ``output/about/index.html``
            ``/docs/intro/``      -> ``output/docs/intro/index.html``
            ``/search``           -> ``output/search/index.html``

        """
        # Normalise: strip leading slash, ensure trailing slash for non-root
        clean = permalink.strip("/")
        if not clean:
            return output_dir / "index.html"
        return output_dir / clean / "index.html"

    @staticmethod
    def _write_html(filepath: Path, html: str) -> int:
        """Write HTML content to a file, creating parent dirs as needed.

        Returns the size in bytes of the written file.

        """
        filepath.parent.mkdir(parents=True, exist_ok=True)
        data = html.encode("utf-8")
        filepath.write_bytes(data)
        return len(data)
