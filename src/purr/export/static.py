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
        """Render all Bengal content pages to HTML files.

        Uses the same rendering path as the live server: builds a Bengal template
        context for each page, resolves the Kida template, and renders to HTML.

        """
        from bengal.rendering.context import build_page_context

        from purr.content.router import _resolve_template_name

        results: list[ExportedFile] = []

        for page in self._site.pages:
            permalink = self._get_page_permalink(page)
            if not permalink:
                continue

            t0 = time.perf_counter()

            template_name = _resolve_template_name(page)
            content = page.html_content or ""
            context = build_page_context(
                page, self._site, content=content, lazy=True,
            )

            try:
                html = self._render_template(template_name, context)
            except Exception as exc:
                msg = (
                    f"Failed to render content page {permalink!r} "
                    f"(template={template_name!r}): {exc}"
                )
                raise ExportError(msg) from exc

            filepath = self._permalink_to_filepath(permalink, output_dir)
            size = self._write_html(filepath, html)
            elapsed = (time.perf_counter() - t0) * 1000

            results.append(ExportedFile(
                source_path=permalink,
                output_path=filepath,
                source_type="content",
                size_bytes=size,
                duration_ms=elapsed,
            ))

        return results

    def _get_page_permalink(self, page: object) -> str | None:
        """Extract the URL path for a Bengal page.

        Mirrors ``ContentRouter._get_permalink`` logic.

        """
        if hasattr(page, "href") and page.href:
            return str(page.href)
        if hasattr(page, "_path") and page._path:
            path = str(page._path)
            if not path.startswith("/"):
                path = "/" + path
            return path
        return None

    def _get_kida_env(self) -> object:
        """Get the Kida template environment, freezing the app if needed."""
        # Freeze the app if not already frozen — this initializes _kida_env
        if hasattr(self._app, "_ensure_frozen"):
            self._app._ensure_frozen()  # noqa: SLF001

        kida_env = (
            getattr(self._app, "_kida_env", None)
            or getattr(self._app, "kida_env", None)
            or getattr(self._app, "template_env", None)
        )
        if kida_env is None:
            msg = "Cannot access Kida template environment from Chirp app"
            raise ExportError(msg)

        return kida_env

    def _render_template(self, template_name: str, context: dict) -> str:
        """Render a Kida template to an HTML string via the Chirp app."""
        kida_env = self._get_kida_env()
        template = kida_env.get_template(template_name)
        return template.render(**context)

    def _render_dynamic_routes(self, output_dir: Path) -> list[ExportedFile]:
        """Pre-render dynamic Chirp routes with default state.

        Only GET handlers are exported.  Routes can opt out by setting
        ``exportable = False`` at module level in the route file.

        Uses Chirp's TestClient to make synthetic requests through the full
        ASGI pipeline, capturing the rendered HTML.

        """
        import asyncio

        # Filter to GET-only, exportable routes
        exportable = [
            defn
            for defn in self._routes
            if "GET" in defn.methods and self._is_exportable(defn)
        ]

        if not exportable:
            return []

        # If we're already inside an event loop (e.g., pytest-asyncio), use
        # a new thread to avoid "cannot call asyncio.run() from running loop".
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No loop running — safe to use asyncio.run()
            return asyncio.run(self._render_routes_async(exportable, output_dir))

        # Running inside an existing loop — use a thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run, self._render_routes_async(exportable, output_dir),
            )
            return future.result()

    @staticmethod
    def _is_exportable(defn: RouteDefinition) -> bool:
        """Check whether a route has opted out of export.

        A route module can set ``exportable = False`` to skip pre-rendering.

        """
        import importlib.util
        import sys

        # The module is already loaded in sys.modules from route discovery
        module_name = None
        for name, mod in sys.modules.items():
            if name.startswith("purr_routes.") and hasattr(mod, "__file__"):
                if mod.__file__ and Path(mod.__file__) == defn.source:
                    module_name = name
                    break

        if module_name is not None:
            module = sys.modules[module_name]
            return getattr(module, "exportable", True) is not False

        # If we can't find the module, default to exportable
        return True

    async def _render_routes_async(
        self,
        routes: list[RouteDefinition],
        output_dir: Path,
    ) -> list[ExportedFile]:
        """Render dynamic routes via Chirp's TestClient."""
        from chirp.testing.client import TestClient

        results: list[ExportedFile] = []

        async with TestClient(self._app) as client:
            for defn in routes:
                t0 = time.perf_counter()

                try:
                    response = await client.get(defn.path)
                except Exception as exc:
                    msg = (
                        f"Failed to pre-render dynamic route {defn.path!r} "
                        f"(source={defn.source}): {exc}"
                    )
                    raise ExportError(msg) from exc

                body = (
                    response.body.decode("utf-8")
                    if isinstance(response.body, bytes)
                    else str(response.body)
                )

                filepath = self._permalink_to_filepath(defn.path, output_dir)
                size = self._write_html(filepath, body)
                elapsed = (time.perf_counter() - t0) * 1000

                results.append(ExportedFile(
                    source_path=defn.path,
                    output_path=filepath,
                    source_type="dynamic",
                    size_bytes=size,
                    duration_ms=elapsed,
                ))

        return results

    def _copy_assets(self, output_dir: Path) -> list[ExportedFile]:
        """Copy static assets to the output directory."""
        from purr.export.assets import copy_assets

        return list(copy_assets(self._config.static_path, output_dir))

    def _render_error_pages(self, output_dir: Path) -> list[ExportedFile]:
        """Render error pages (404, etc.) if templates exist.

        Checks the Kida environment for a ``404.html`` template.  If found,
        renders it with site-level context and writes to ``output/404.html``.
        Skips silently if the template does not exist.

        """
        results: list[ExportedFile] = []

        try:
            kida_env = self._get_kida_env()
        except ExportError:
            return results

        # Try to render 404 page
        try:
            template = kida_env.get_template("404.html")
        except Exception:  # noqa: BLE001
            # Template doesn't exist — skip silently
            return results

        t0 = time.perf_counter()

        # Build minimal site-level context
        context: dict[str, object] = {
            "site": self._site,
            "title": "Page Not Found",
        }

        try:
            html = template.render(**context)
        except Exception as exc:
            msg = f"Failed to render 404 page: {exc}"
            raise ExportError(msg) from exc

        filepath = output_dir / "404.html"
        size = self._write_html(filepath, html)
        elapsed = (time.perf_counter() - t0) * 1000

        results.append(ExportedFile(
            source_path="/404.html",
            output_path=filepath,
            source_type="error_page",
            size_bytes=size,
            duration_ms=elapsed,
        ))

        return results

    def _generate_sitemap(
        self,
        output_dir: Path,
        exported: list[ExportedFile],
    ) -> list[ExportedFile]:
        """Generate sitemap.xml from exported pages."""
        from purr.export.sitemap import write_sitemap

        base_url = getattr(self._config, "base_url", "")
        result = write_sitemap(exported, base_url, output_dir)
        if result is not None:
            return [result]
        return []

    def _fingerprint_assets(self, output_dir: Path) -> None:
        """Hash asset filenames and rewrite HTML references."""
        from purr.export.assets import (
            fingerprint_assets,
            rewrite_asset_refs,
            write_manifest,
        )

        manifest = fingerprint_assets(output_dir)
        if manifest:
            rewrite_asset_refs(output_dir, manifest)
            write_manifest(output_dir, manifest)

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
