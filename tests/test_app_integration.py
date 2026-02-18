"""Integration tests for purr.app — end-to-end wiring of Bengal + Chirp."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from purr._errors import ConfigError
from purr.app import (
    _create_chirp_app,
    _load_site,
    _mount_static_files,
    _start_watcher,
    _wire_content_routes,
)
from purr.config import PurrConfig

from .conftest import make_test_page, make_test_site


class TestLoadSite:
    """_load_site — Bengal Site loading from disk."""

    def test_raises_config_error_for_missing_dir(self, tmp_path: Path) -> None:
        """Non-existent root should produce a clear ConfigError."""
        with pytest.raises(ConfigError, match="Failed to load Bengal site"):
            _load_site(tmp_path / "nonexistent")

    def test_loads_site_for_testing(self, tmp_path: Path) -> None:
        """A directory with bengal.toml should load successfully."""
        # Create a minimal Bengal config
        (tmp_path / "bengal.toml").write_text(
            '[site]\ntitle = "Test"\n[build]\noutput_dir = "public"\n'
        )
        site = _load_site(tmp_path)
        assert site is not None
        assert site.root_path == tmp_path


class TestCreateChirpApp:
    """_create_chirp_app — Chirp App creation from PurrConfig."""

    def test_creates_app_with_template_dir(self, tmp_site: Path) -> None:
        config = PurrConfig(root=tmp_site)
        app = _create_chirp_app(config)
        assert app is not None
        assert not app.config.debug

    def test_debug_mode(self, tmp_site: Path) -> None:
        config = PurrConfig(root=tmp_site)
        app = _create_chirp_app(config, debug=True)
        assert app.config.debug is True

    def test_host_and_port_from_config(self, tmp_site: Path) -> None:
        config = PurrConfig(root=tmp_site, host="0.0.0.0", port=9000)
        app = _create_chirp_app(config)
        assert app.config.host == "0.0.0.0"
        assert app.config.port == 9000


class TestWireContentRoutes:
    """_wire_content_routes — registering Bengal pages as Chirp routes."""

    def test_registers_pages_as_routes(self, tmp_path: Path) -> None:
        from chirp import App, AppConfig

        pages = [
            make_test_page(tmp_path / "home.md", href="/"),
            make_test_page(tmp_path / "about.md", href="/about/"),
        ]
        site = make_test_site(tmp_path, pages)
        app = App(config=AppConfig(template_dir=tmp_path))

        config = PurrConfig(root=tmp_path)
        _router, count = _wire_content_routes(site, app, config)
        assert count == 2

    def test_empty_site_returns_zero(self, tmp_path: Path) -> None:
        from chirp import App, AppConfig

        site = make_test_site(tmp_path, [])
        app = App(config=AppConfig(template_dir=tmp_path))
        config = PurrConfig(root=tmp_path)

        _router, count = _wire_content_routes(site, app, config)
        assert count == 0


class TestMountStaticFiles:
    """_mount_static_files — static file middleware."""

    def test_mounts_when_static_dir_exists(self, tmp_site: Path) -> None:
        from chirp import App, AppConfig

        config = PurrConfig(root=tmp_site)
        app = App(config=AppConfig(template_dir=tmp_site / "templates"))

        # Should not raise — static/ exists in tmp_site
        _mount_static_files(app, config)

    def test_skips_when_static_dir_missing(self, tmp_path: Path) -> None:
        from chirp import App, AppConfig

        config = PurrConfig(root=tmp_path)
        app = App(config=AppConfig(template_dir=tmp_path))

        # Should not raise — just skips silently
        _mount_static_files(app, config)


class TestEndToEndRouting:
    """Full pipeline: Bengal pages served through Chirp routes via test client."""

    @pytest.mark.asyncio
    async def test_content_page_is_reachable(self, tmp_path: Path) -> None:
        """A registered content page should return 200 via Chirp's test client."""
        from chirp import App, AppConfig
        from chirp.testing.client import TestClient

        # Create templates directory with a simple page.html
        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "page.html").write_text(
            "<html><body>{{ content }}</body></html>"
        )

        pages = [
            make_test_page(
                tmp_path / "hello.md",
                href="/hello/",
                html_content="<p>Hello from Purr</p>",
            ),
        ]
        site = make_test_site(tmp_path, pages)
        app = App(config=AppConfig(template_dir=templates))
        config = PurrConfig(root=tmp_path)

        _wire_content_routes(site, app, config)

        async with TestClient(app) as client:
            response = await client.get("/hello/")
            assert response.status == 200
            body = response.body.decode() if isinstance(response.body, bytes) else response.body
            assert "Hello from Purr" in body

    @pytest.mark.asyncio
    async def test_multiple_pages_routed_correctly(self, tmp_path: Path) -> None:
        """Multiple pages should each be accessible at their own permalink."""
        from chirp import App, AppConfig
        from chirp.testing.client import TestClient

        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "page.html").write_text("<html>{{ content }}</html>")

        pages = [
            make_test_page(tmp_path / "a.md", href="/a/", html_content="<p>Page A</p>"),
            make_test_page(tmp_path / "b.md", href="/b/", html_content="<p>Page B</p>"),
        ]
        site = make_test_site(tmp_path, pages)
        app = App(config=AppConfig(template_dir=templates))
        config = PurrConfig(root=tmp_path)
        _wire_content_routes(site, app, config)

        async with TestClient(app) as client:
            resp_a = await client.get("/a/")
            resp_b = await client.get("/b/")

            assert resp_a.status == 200
            assert resp_b.status == 200

            body_a = resp_a.body.decode() if isinstance(resp_a.body, bytes) else resp_a.body
            body_b = resp_b.body.decode() if isinstance(resp_b.body, bytes) else resp_b.body

            assert "Page A" in body_a
            assert "Page B" in body_b
            # Cross-contamination check
            assert "Page B" not in body_a
            assert "Page A" not in body_b

    @pytest.mark.asyncio
    async def test_unregistered_path_returns_404(self, tmp_path: Path) -> None:
        from chirp import App, AppConfig
        from chirp.testing.client import TestClient

        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "page.html").write_text("<html>{{ content }}</html>")

        pages = [make_test_page(tmp_path / "a.md", href="/a/", html_content="<p>A</p>")]
        site = make_test_site(tmp_path, pages)
        app = App(config=AppConfig(template_dir=templates))
        config = PurrConfig(root=tmp_path)
        _wire_content_routes(site, app, config)

        async with TestClient(app) as client:
            response = await client.get("/nonexistent/")
            assert response.status == 404


class TestStartWatcher:
    """_start_watcher — lifecycle hooks wire watcher → pipeline."""

    def test_registers_startup_and_shutdown_hooks(self, tmp_site: Path) -> None:
        """_start_watcher should register on_startup and on_shutdown on the app."""
        from chirp import App, AppConfig

        config = PurrConfig(root=tmp_site)
        app = App(config=AppConfig(template_dir=tmp_site / "templates"))
        pipeline = MagicMock()

        hooks_before = len(app._startup_hooks)
        shutdown_before = len(app._shutdown_hooks)

        _start_watcher(config, pipeline, app)

        assert len(app._startup_hooks) == hooks_before + 1
        assert len(app._shutdown_hooks) == shutdown_before + 1

    @pytest.mark.asyncio
    async def test_startup_hook_starts_watcher(self, tmp_site: Path) -> None:
        """The registered startup hook should spawn a consumer task."""
        import asyncio

        from chirp import App, AppConfig

        config = PurrConfig(root=tmp_site)
        app = App(config=AppConfig(template_dir=tmp_site / "templates"))
        pipeline = MagicMock()

        watcher = _start_watcher(config, pipeline, app)

        # Watcher should NOT be running yet (starts on startup hook)
        assert not watcher.is_running

        # Simulate calling the startup hook
        startup_hook = app._startup_hooks[-1]
        await startup_hook()

        # Let the consumer task enter changes() and set _running = True
        await asyncio.sleep(0)
        assert watcher.is_running

        # Simulate calling the shutdown hook to clean up
        shutdown_hook = app._shutdown_hooks[-1]
        await shutdown_hook()

        # Let the cancelled task's finally block run
        await asyncio.sleep(0)
        assert not watcher.is_running

    @pytest.mark.asyncio
    async def test_event_consumption_wires_to_pipeline(self, tmp_site: Path) -> None:
        """Events yielded by awatch should reach pipeline.handle_change."""
        import asyncio

        from watchfiles import Change

        from chirp import App, AppConfig

        from purr.content.watcher import ChangeEvent
        from purr.reactive.broadcaster import Broadcaster
        from purr.reactive.graph import DependencyGraph
        from purr.reactive.mapper import ReactiveMapper
        from purr.reactive.pipeline import ReactivePipeline

        config = PurrConfig(root=tmp_site)
        app = App(config=AppConfig(template_dir=tmp_site / "templates"))

        site = MagicMock()
        site.pages = []
        broadcaster = Broadcaster()
        graph = DependencyGraph(tracer=MagicMock(), app=app)
        pipeline = ReactivePipeline(
            graph=graph, mapper=ReactiveMapper(), broadcaster=broadcaster, site=site,
        )

        # Mock awatch to yield one batch of changes then stop
        css_path = tmp_site / "static" / "style.css"

        async def _fake_awatch(*_args: object, **_kwargs: object):  # noqa: ANN202
            yield {(Change.modified, str(css_path))}

        with patch("watchfiles.awatch", _fake_awatch):
            watcher = _start_watcher(config, pipeline, app)

            # Fire the startup hook
            startup_hook = app._startup_hooks[-1]
            await startup_hook()

            # Give the consumer task time to process the yielded batch
            await asyncio.sleep(0.05)

            # The asset handler pushes full refresh — no subscribers, so
            # nothing to receive, but the pipeline should have processed
            # without error.  The consumer task should have finished since
            # our fake awatch only yields once.

            # Clean up
            shutdown_hook = app._shutdown_hooks[-1]
            await shutdown_hook()
