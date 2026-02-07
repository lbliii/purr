"""Integration tests for Phase 3 — dynamic routes alongside static content."""

from pathlib import Path

import pytest

from purr.app import (
    _create_chirp_app,
    _wire_content_routes,
    _wire_dynamic_routes,
)
from purr.config import PurrConfig

from .conftest import make_test_page, make_test_site


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def site_with_routes(tmp_path: Path) -> Path:
    """Create a full site with content, templates, and routes."""
    # Content
    content = tmp_path / "content"
    content.mkdir()
    (content / "_index.md").write_text(
        "---\ntitle: Home\n---\n\n# Welcome\n"
    )

    # Templates
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "page.html").write_text(
        "<html><body>{{ content }}</body></html>"
    )
    (templates / "index.html").write_text(
        "<html><body>{{ content }}</body></html>"
    )
    (templates / "search.html").write_text(
        "<html><body>Search: {{ query }}</body></html>"
    )

    # Routes
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "search.py").write_text(
        "async def get(request):\n"
        "    from chirp import Response\n"
        "    return Response(body=b'search results', content_type='text/plain')\n"
    )
    (routes / "health.py").write_text(
        "async def get(request):\n"
        "    from chirp import Response\n"
        "    return Response(body=b'ok', content_type='text/plain')\n"
    )

    return tmp_path


# ---------------------------------------------------------------------------
# _wire_dynamic_routes unit tests
# ---------------------------------------------------------------------------


class TestWireDynamicRoutes:
    """Unit tests for _wire_dynamic_routes."""

    def test_wires_routes_from_directory(self, site_with_routes: Path) -> None:
        config = PurrConfig(root=site_with_routes)
        app = _create_chirp_app(config)

        defs = _wire_dynamic_routes(app, config)
        assert len(defs) == 2
        paths = {d.path for d in defs}
        assert "/search" in paths
        assert "/health" in paths

    def test_returns_empty_when_no_routes_dir(self, tmp_path: Path) -> None:
        config = PurrConfig(root=tmp_path)
        app = _create_chirp_app(config)

        defs = _wire_dynamic_routes(app, config)
        assert defs == ()

    def test_injects_nav_entries_into_template_globals(
        self, site_with_routes: Path,
    ) -> None:
        config = PurrConfig(root=site_with_routes)
        app = _create_chirp_app(config)

        _wire_dynamic_routes(app, config)
        nav = app._template_globals.get("dynamic_routes")
        assert nav is not None
        assert len(nav) == 2
        paths = {e.path for e in nav}
        assert "/search" in paths
        assert "/health" in paths

    def test_no_nav_globals_when_no_routes(self, tmp_path: Path) -> None:
        config = PurrConfig(root=tmp_path)
        app = _create_chirp_app(config)

        _wire_dynamic_routes(app, config)
        assert "dynamic_routes" not in app._template_globals


# ---------------------------------------------------------------------------
# Mixed static + dynamic routes
# ---------------------------------------------------------------------------


class TestMixedRoutes:
    """Integration: content routes and dynamic routes coexisting."""

    @pytest.mark.asyncio
    async def test_both_content_and_dynamic_reachable(
        self, site_with_routes: Path,
    ) -> None:
        """Content pages and dynamic routes should both return 200."""
        from chirp.testing.client import TestClient

        config = PurrConfig(root=site_with_routes)
        app = _create_chirp_app(config, debug=True)

        pages = [
            make_test_page(
                site_with_routes / "content" / "_index.md",
                href="/",
                html_content="<p>Home</p>",
            ),
        ]
        site = make_test_site(site_with_routes, pages)
        _wire_content_routes(site, app)
        _wire_dynamic_routes(app, config)

        async with TestClient(app) as client:
            # Content route
            resp_home = await client.get("/")
            assert resp_home.status == 200

            # Dynamic routes
            resp_search = await client.get("/search")
            assert resp_search.status == 200
            body = (
                resp_search.body.decode()
                if isinstance(resp_search.body, bytes)
                else resp_search.body
            )
            assert "search results" in body

            resp_health = await client.get("/health")
            assert resp_health.status == 200

    @pytest.mark.asyncio
    async def test_unknown_path_returns_404(self, site_with_routes: Path) -> None:
        """Paths not matching any content or dynamic route return 404."""
        from chirp.testing.client import TestClient

        config = PurrConfig(root=site_with_routes)
        app = _create_chirp_app(config, debug=True)

        pages = [
            make_test_page(
                site_with_routes / "content" / "_index.md",
                href="/",
                html_content="<p>Home</p>",
            ),
        ]
        site = make_test_site(site_with_routes, pages)
        _wire_content_routes(site, app)
        _wire_dynamic_routes(app, config)

        async with TestClient(app) as client:
            resp = await client.get("/nonexistent")
            assert resp.status == 404

    @pytest.mark.asyncio
    async def test_dynamic_route_receives_request(
        self, tmp_path: Path,
    ) -> None:
        """Dynamic route handler receives a valid Request with query params."""
        from chirp.testing.client import TestClient

        templates = tmp_path / "templates"
        templates.mkdir()

        routes = tmp_path / "routes"
        routes.mkdir()
        (routes / "echo.py").write_text(
            "async def get(request):\n"
            "    from chirp import Response\n"
            "    q = request.query.get('msg', 'none')\n"
            "    return Response(body=q.encode(), content_type='text/plain')\n"
        )

        config = PurrConfig(root=tmp_path)
        app = _create_chirp_app(config, debug=True)
        _wire_dynamic_routes(app, config)

        async with TestClient(app) as client:
            resp = await client.get("/echo?msg=hello")
            assert resp.status == 200
            body = (
                resp.body.decode()
                if isinstance(resp.body, bytes)
                else resp.body
            )
            assert "hello" in body


# ---------------------------------------------------------------------------
# Site accessor from dynamic routes
# ---------------------------------------------------------------------------


class TestSiteAccessFromRoutes:
    """Dynamic route handlers can access purr.site."""

    @pytest.mark.asyncio
    async def test_handler_can_read_site(self, tmp_path: Path) -> None:
        """A handler importing purr.site gets the loaded Bengal Site."""
        import purr
        from purr import _set_site

        from chirp.testing.client import TestClient

        templates = tmp_path / "templates"
        templates.mkdir()

        routes = tmp_path / "routes"
        routes.mkdir()
        (routes / "info.py").write_text(
            "async def get(request):\n"
            "    import purr\n"
            "    from chirp import Response\n"
            "    title = getattr(purr.site, 'title', 'unknown')\n"
            "    return Response(body=title.encode(), content_type='text/plain')\n"
        )

        site = make_test_site(tmp_path, config={"site": {"title": "My Site"}})
        _set_site(site)

        try:
            config = PurrConfig(root=tmp_path)
            app = _create_chirp_app(config, debug=True)
            _wire_dynamic_routes(app, config)

            async with TestClient(app) as client:
                resp = await client.get("/info")
                assert resp.status == 200
        finally:
            purr._site_ref = None
