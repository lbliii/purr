"""Integration tests for the static export pipeline.

Tests the full StaticExporter pipeline against a realistic site structure
with content pages, dynamic routes, static assets, templates, and optional
features (sitemap, 404, fingerprinting).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from purr.config import PurrConfig
from purr.export.static import StaticExporter

from .conftest import make_test_page, make_test_site


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def full_site(tmp_path: Path) -> Path:
    """Create a realistic site with content, templates, static, and routes."""
    # Content
    content = tmp_path / "content"
    content.mkdir()
    (content / "_index.md").write_text(
        "---\ntitle: Home\n---\n\n# Welcome\n\nHome page content.\n"
    )
    docs = content / "docs"
    docs.mkdir()
    (docs / "getting-started.md").write_text(
        "---\ntitle: Getting Started\n---\n\n# Getting Started\n\nIntro text.\n"
    )

    # Templates
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "page.html").write_text(
        '<!DOCTYPE html>\n<html>\n<head><link href="/static/style.css"></head>\n'
        "<body>{{ content }}</body>\n</html>\n"
    )
    (templates / "index.html").write_text(
        '<!DOCTYPE html>\n<html>\n<head><link href="/static/style.css"></head>\n'
        "<body>{{ content }}</body>\n</html>\n"
    )
    (templates / "404.html").write_text(
        "<!DOCTYPE html>\n<html>\n<body><h1>Not Found</h1></body>\n</html>\n"
    )

    # Static assets
    static = tmp_path / "static"
    static.mkdir()
    (static / "style.css").write_text("body { margin: 0; font-family: sans-serif; }\n")
    img = static / "img"
    img.mkdir()
    (img / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    # Dynamic routes
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "search.py").write_text(
        'from chirp import Response\n\n'
        'async def get(request):\n'
        '    return Response(body=b"<html><body>Search results</body></html>")\n'
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Full pipeline tests
# ---------------------------------------------------------------------------


class TestBuildPipeline:
    """Full export pipeline with mixed content + dynamic + assets."""

    def test_exports_content_pages(self, tmp_path: Path) -> None:
        """Content pages should be rendered to the correct output paths."""
        from chirp import App, AppConfig

        pages = [
            make_test_page(tmp_path / "home.md", href="/", html_content="<p>Home</p>"),
            make_test_page(
                tmp_path / "about.md", href="/about/", html_content="<p>About</p>",
            ),
        ]
        site = make_test_site(tmp_path, pages)

        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "page.html").write_text("<html>{{ content }}</html>")

        output = tmp_path / "dist"
        config = PurrConfig(root=tmp_path, output=output)

        app = App(config=AppConfig(template_dir=templates))

        exporter = StaticExporter(site=site, app=app, config=config)
        result = exporter.export()

        assert result.total_pages == 2
        assert (output / "index.html").exists()
        assert (output / "about" / "index.html").exists()
        assert "<p>Home</p>" in (output / "index.html").read_text()
        assert "<p>About</p>" in (output / "about" / "index.html").read_text()

    def test_copies_static_assets(self, tmp_path: Path) -> None:
        """Static assets should be copied preserving directory structure."""
        site = make_test_site(tmp_path, [])

        templates = tmp_path / "templates"
        templates.mkdir()

        static = tmp_path / "static"
        static.mkdir()
        (static / "style.css").write_text("body { color: red; }")
        (static / "img").mkdir()
        (static / "img" / "logo.png").write_bytes(b"PNG")

        output = tmp_path / "dist"
        config = PurrConfig(root=tmp_path, output=output)

        from chirp import App, AppConfig

        app = App(config=AppConfig(template_dir=templates))

        exporter = StaticExporter(site=site, app=app, config=config)
        result = exporter.export()

        assert result.total_assets == 2
        assert (output / "static" / "style.css").exists()
        assert (output / "static" / "img" / "logo.png").exists()

    def test_generates_sitemap_with_base_url(self, tmp_path: Path) -> None:
        """Sitemap.xml should be generated when base_url is configured."""
        pages = [
            make_test_page(tmp_path / "home.md", href="/", html_content="<p>Home</p>"),
        ]
        site = make_test_site(tmp_path, pages)

        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "page.html").write_text("<html>{{ content }}</html>")

        output = tmp_path / "dist"
        config = PurrConfig(
            root=tmp_path, output=output, base_url="https://example.com",
        )

        from chirp import App, AppConfig

        app = App(config=AppConfig(template_dir=templates))

        exporter = StaticExporter(site=site, app=app, config=config)
        result = exporter.export()

        sitemap_files = [f for f in result.files if f.source_type == "sitemap"]
        assert len(sitemap_files) == 1
        assert (output / "sitemap.xml").exists()

        xml = (output / "sitemap.xml").read_text()
        assert "https://example.com/" in xml

    def test_skips_sitemap_without_base_url(self, tmp_path: Path) -> None:
        """Sitemap should be skipped when base_url is empty."""
        site = make_test_site(tmp_path, [])

        templates = tmp_path / "templates"
        templates.mkdir()

        output = tmp_path / "dist"
        config = PurrConfig(root=tmp_path, output=output)

        from chirp import App, AppConfig

        app = App(config=AppConfig(template_dir=templates))

        exporter = StaticExporter(site=site, app=app, config=config)
        result = exporter.export()

        sitemap_files = [f for f in result.files if f.source_type == "sitemap"]
        assert len(sitemap_files) == 0

    def test_renders_404_page(self, tmp_path: Path) -> None:
        """404.html should be generated when the template exists."""
        site = make_test_site(tmp_path, [])

        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "404.html").write_text("<html><body>Not Found</body></html>")

        output = tmp_path / "dist"
        config = PurrConfig(root=tmp_path, output=output)

        from chirp import App, AppConfig

        app = App(config=AppConfig(template_dir=templates))

        exporter = StaticExporter(site=site, app=app, config=config)
        result = exporter.export()

        error_files = [f for f in result.files if f.source_type == "error_page"]
        assert len(error_files) == 1
        assert (output / "404.html").exists()
        assert "Not Found" in (output / "404.html").read_text()

    def test_cleans_output_before_export(self, tmp_path: Path) -> None:
        """Output directory should be wiped before export."""
        site = make_test_site(tmp_path, [])

        templates = tmp_path / "templates"
        templates.mkdir()

        output = tmp_path / "dist"
        output.mkdir()
        stale = output / "stale.html"
        stale.write_text("old content")

        config = PurrConfig(root=tmp_path, output=output)

        from chirp import App, AppConfig

        app = App(config=AppConfig(template_dir=templates))

        exporter = StaticExporter(site=site, app=app, config=config)
        exporter.export()

        assert not stale.exists()

    def test_export_result_has_positive_duration(self, tmp_path: Path) -> None:
        """Export duration should be non-negative."""
        site = make_test_site(tmp_path, [])

        templates = tmp_path / "templates"
        templates.mkdir()

        output = tmp_path / "dist"
        config = PurrConfig(root=tmp_path, output=output)

        from chirp import App, AppConfig

        app = App(config=AppConfig(template_dir=templates))

        exporter = StaticExporter(site=site, app=app, config=config)
        result = exporter.export()

        assert result.duration_ms >= 0
        assert result.output_dir == output


# ---------------------------------------------------------------------------
# Fingerprinting integration
# ---------------------------------------------------------------------------


class TestFingerprintIntegration:
    """Asset fingerprinting rewrites HTML references end-to-end."""

    def test_fingerprint_rewrites_html(self, tmp_path: Path) -> None:
        pages = [
            make_test_page(tmp_path / "p.md", href="/", html_content="<p>Hi</p>"),
        ]
        site = make_test_site(tmp_path, pages)

        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "page.html").write_text(
            '<html><link href="/static/style.css">{{ content }}</html>'
        )

        static = tmp_path / "static"
        static.mkdir()
        (static / "style.css").write_text("body { margin: 0; }")

        output = tmp_path / "dist"
        config = PurrConfig(root=tmp_path, output=output, fingerprint=True)

        from chirp import App, AppConfig

        app = App(config=AppConfig(template_dir=templates))

        exporter = StaticExporter(site=site, app=app, config=config)
        result = exporter.export()

        # HTML should have fingerprinted references
        html = (output / "index.html").read_text()
        assert "/static/style.css" not in html
        assert "/static/style." in html
        assert ".css" in html

        # Original style.css should NOT exist (renamed)
        assert not (output / "static" / "style.css").exists()

        # Manifest should exist
        assert (output / "manifest.json").exists()


# ---------------------------------------------------------------------------
# Dynamic route pre-rendering
# ---------------------------------------------------------------------------


class TestDynamicRouteExport:
    """Pre-rendering dynamic routes through the ASGI pipeline."""

    @pytest.mark.asyncio
    async def test_prerender_get_route(self, tmp_path: Path) -> None:
        """GET dynamic routes should be pre-rendered to static files."""
        from chirp import App, AppConfig, Response

        from purr.routes.loader import RouteDefinition

        templates = tmp_path / "templates"
        templates.mkdir()

        app = App(config=AppConfig(template_dir=templates))

        async def search_handler(request):  # noqa: ARG001
            return Response(body=b"<html>Search results</html>")

        app.route("/search", name="search")(search_handler)

        route_source = tmp_path / "routes" / "search.py"
        route_source.parent.mkdir(parents=True, exist_ok=True)
        route_source.write_text("# stub")

        route_def = RouteDefinition(
            path="/search",
            handler=search_handler,
            methods=("GET",),
            name="search",
            source=route_source,
            nav_title="Search",
        )

        output = tmp_path / "dist"
        config = PurrConfig(root=tmp_path, output=output)
        site = make_test_site(tmp_path, [])

        exporter = StaticExporter(
            site=site, app=app, config=config, routes=(route_def,),
        )
        result = exporter.export()

        dynamic_files = [f for f in result.files if f.source_type == "dynamic"]
        assert len(dynamic_files) == 1
        assert (output / "search" / "index.html").exists()
        assert "Search results" in (output / "search" / "index.html").read_text()

    @pytest.mark.asyncio
    async def test_skips_non_get_routes(self, tmp_path: Path) -> None:
        """POST/PUT/DELETE routes should not be pre-rendered."""
        from chirp import App, AppConfig, Response

        from purr.routes.loader import RouteDefinition

        templates = tmp_path / "templates"
        templates.mkdir()

        app = App(config=AppConfig(template_dir=templates))

        async def post_handler(request):  # noqa: ARG001
            return Response(body=b"created")

        app.route("/api/submit", methods=["POST"], name="submit")(post_handler)

        route_def = RouteDefinition(
            path="/api/submit",
            handler=post_handler,
            methods=("POST",),
            name="submit",
            source=tmp_path / "routes" / "submit.py",
            nav_title=None,
        )

        output = tmp_path / "dist"
        config = PurrConfig(root=tmp_path, output=output)
        site = make_test_site(tmp_path, [])

        exporter = StaticExporter(
            site=site, app=app, config=config, routes=(route_def,),
        )
        result = exporter.export()

        dynamic_files = [f for f in result.files if f.source_type == "dynamic"]
        assert len(dynamic_files) == 0


# ---------------------------------------------------------------------------
# Build parity
# ---------------------------------------------------------------------------


class TestBuildParity:
    """Content page export should match live rendering."""

    @pytest.mark.asyncio
    async def test_content_matches_live(self, tmp_path: Path) -> None:
        """Exported HTML should be identical to what the test client returns."""
        from chirp import App, AppConfig
        from chirp.testing.client import TestClient

        from purr.app import _wire_content_routes

        pages = [
            make_test_page(
                tmp_path / "hello.md",
                href="/hello/",
                html_content="<p>Hello World</p>",
            ),
        ]
        site = make_test_site(tmp_path, pages)

        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "page.html").write_text(
            "<html><body>{{ content }}</body></html>"
        )

        app = App(config=AppConfig(template_dir=templates))
        config = PurrConfig(root=tmp_path, output=tmp_path / "dist")
        _wire_content_routes(site, app, config)

        # Get live response
        async with TestClient(app) as client:
            live_response = await client.get("/hello/")
            live_html = (
                live_response.body.decode("utf-8")
                if isinstance(live_response.body, bytes)
                else str(live_response.body)
            )

        # Get exported response
        output = tmp_path / "dist"

        # Create a fresh app for the exporter (same config)
        export_app = App(config=AppConfig(template_dir=templates))
        _wire_content_routes(site, export_app, config)

        exporter = StaticExporter(site=site, app=export_app, config=config)
        result = exporter.export()

        exported_html = (output / "hello" / "index.html").read_text()

        assert exported_html == live_html
        assert result.total_pages == 1
