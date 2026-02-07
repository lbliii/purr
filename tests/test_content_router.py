"""Tests for purr.content.router — ContentRouter and template resolution."""

from __future__ import annotations

from pathlib import Path

from purr.content.router import ContentRouter, _resolve_template_name

from .conftest import make_test_page, make_test_site


class TestResolveTemplateName:
    """Template name resolution: frontmatter > index detection > default."""

    def test_explicit_template_in_metadata(self, tmp_path: Path) -> None:
        page = make_test_page(
            tmp_path / "page.md",
            href="/page/",
            metadata={"title": "Custom", "template": "custom.html"},
        )
        assert _resolve_template_name(page) == "custom.html"

    def test_index_page_uses_index_template(self, tmp_path: Path) -> None:
        page = make_test_page(tmp_path / "_index.md", href="/")
        assert _resolve_template_name(page) == "index.html"

    def test_regular_page_uses_page_template(self, tmp_path: Path) -> None:
        page = make_test_page(tmp_path / "about.md", href="/about/")
        assert _resolve_template_name(page) == "page.html"

    def test_explicit_template_overrides_index_detection(self, tmp_path: Path) -> None:
        page = make_test_page(
            tmp_path / "_index.md",
            href="/",
            metadata={"title": "Home", "template": "home.html"},
        )
        assert _resolve_template_name(page) == "home.html"


class TestContentRouter:
    """ContentRouter — registers Bengal pages as Chirp routes."""

    def test_register_pages_creates_routes(self, tmp_path: Path) -> None:
        """Each page in site.pages gets a Chirp route at its permalink."""
        from chirp import App, AppConfig

        pages = [
            make_test_page(tmp_path / "home.md", href="/"),
            make_test_page(tmp_path / "about.md", href="/about/"),
            make_test_page(tmp_path / "docs" / "intro.md", href="/docs/intro/"),
        ]
        site = make_test_site(tmp_path, pages)
        app = App(config=AppConfig(template_dir=tmp_path))

        router = ContentRouter(site, app)
        router.register_pages()

        assert router.page_count == 3

    def test_page_count_starts_at_zero(self, tmp_path: Path) -> None:
        from chirp import App, AppConfig

        site = make_test_site(tmp_path, [])
        app = App(config=AppConfig(template_dir=tmp_path))

        router = ContentRouter(site, app)
        assert router.page_count == 0

    def test_empty_site_registers_no_routes(self, tmp_path: Path) -> None:
        from chirp import App, AppConfig

        site = make_test_site(tmp_path, [])
        app = App(config=AppConfig(template_dir=tmp_path))

        router = ContentRouter(site, app)
        router.register_pages()

        assert router.page_count == 0

    def test_bare_page_still_gets_route(self, tmp_path: Path) -> None:
        """A Page with no explicit href still gets a route via Bengal's fallback."""
        from bengal.core.page import Page
        from chirp import App, AppConfig

        # Bengal's href property always returns something (falls back to /)
        page = Page(source_path=tmp_path / "orphan.md")
        site = make_test_site(tmp_path, [page])
        app = App(config=AppConfig(template_dir=tmp_path))

        router = ContentRouter(site, app)
        router.register_pages()

        assert router.page_count == 1

    def test_route_handler_is_async(self, tmp_path: Path) -> None:
        """Page handlers must be async for Chirp's ASGI pipeline."""
        import inspect

        from chirp import App, AppConfig

        page = make_test_page(tmp_path / "page.md", href="/page/")
        site = make_test_site(tmp_path, [page])
        app = App(config=AppConfig(template_dir=tmp_path))

        router = ContentRouter(site, app)
        handler = router._make_page_handler(page, "page.html")

        assert inspect.iscoroutinefunction(handler)
