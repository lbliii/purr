"""Tests for purr.export.static — StaticExporter and data types."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from purr._errors import ExportError
from purr.config import PurrConfig
from purr.export.static import ExportedFile, ExportResult, StaticExporter


# ---------------------------------------------------------------------------
# Data type tests
# ---------------------------------------------------------------------------


class TestExportedFile:
    """ExportedFile — frozen dataclass with correct fields."""

    def test_frozen(self) -> None:
        ef = ExportedFile(
            source_path="/",
            output_path=Path("/out/index.html"),
            source_type="content",
            size_bytes=100,
            duration_ms=1.5,
        )
        with pytest.raises(AttributeError):
            ef.source_path = "/other"  # type: ignore[misc]

    def test_field_access(self) -> None:
        ef = ExportedFile(
            source_path="/docs/",
            output_path=Path("/out/docs/index.html"),
            source_type="dynamic",
            size_bytes=256,
            duration_ms=3.2,
        )
        assert ef.source_path == "/docs/"
        assert ef.source_type == "dynamic"
        assert ef.size_bytes == 256

    def test_equality(self) -> None:
        a = ExportedFile("/", Path("/x"), "content", 10, 1.0)
        b = ExportedFile("/", Path("/x"), "content", 10, 1.0)
        assert a == b


class TestExportResult:
    """ExportResult — aggregate fields."""

    def test_frozen(self) -> None:
        er = ExportResult(
            files=(),
            total_pages=0,
            total_assets=0,
            duration_ms=0.0,
            output_dir=Path("/out"),
        )
        with pytest.raises(AttributeError):
            er.total_pages = 5  # type: ignore[misc]

    def test_aggregate_fields(self) -> None:
        f1 = ExportedFile("/a/", Path("/o/a"), "content", 10, 1.0)
        f2 = ExportedFile("/static/s.css", Path("/o/s"), "asset", 20, 0.5)
        er = ExportResult(
            files=(f1, f2),
            total_pages=1,
            total_assets=1,
            duration_ms=5.0,
            output_dir=Path("/out"),
        )
        assert er.total_pages == 1
        assert er.total_assets == 1
        assert len(er.files) == 2


# ---------------------------------------------------------------------------
# Permalink-to-filepath conversion
# ---------------------------------------------------------------------------


class TestPermalinkToFilepath:
    """StaticExporter._permalink_to_filepath — clean URL convention."""

    def test_root_path(self, tmp_path: Path) -> None:
        result = StaticExporter._permalink_to_filepath("/", tmp_path)
        assert result == tmp_path / "index.html"

    def test_simple_path(self, tmp_path: Path) -> None:
        result = StaticExporter._permalink_to_filepath("/about/", tmp_path)
        assert result == tmp_path / "about" / "index.html"

    def test_nested_path(self, tmp_path: Path) -> None:
        result = StaticExporter._permalink_to_filepath("/docs/intro/", tmp_path)
        assert result == tmp_path / "docs" / "intro" / "index.html"

    def test_path_without_trailing_slash(self, tmp_path: Path) -> None:
        result = StaticExporter._permalink_to_filepath("/search", tmp_path)
        assert result == tmp_path / "search" / "index.html"

    def test_bare_slash_only(self, tmp_path: Path) -> None:
        result = StaticExporter._permalink_to_filepath("/", tmp_path)
        assert result == tmp_path / "index.html"


# ---------------------------------------------------------------------------
# Write helper
# ---------------------------------------------------------------------------


class TestWriteHtml:
    """StaticExporter._write_html — file writing with directory creation."""

    def test_writes_file(self, tmp_path: Path) -> None:
        filepath = tmp_path / "out" / "page" / "index.html"
        size = StaticExporter._write_html(filepath, "<html>test</html>")
        assert filepath.exists()
        assert filepath.read_text() == "<html>test</html>"
        assert size == len("<html>test</html>".encode("utf-8"))

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        filepath = tmp_path / "deep" / "nested" / "dir" / "index.html"
        StaticExporter._write_html(filepath, "content")
        assert filepath.exists()


# ---------------------------------------------------------------------------
# Output cleaning
# ---------------------------------------------------------------------------


class TestOutputCleaning:
    """StaticExporter._clean_output — wipes and recreates output dir."""

    def test_cleans_existing_directory(self, tmp_path: Path) -> None:
        out = tmp_path / "dist"
        out.mkdir()
        (out / "old.html").write_text("stale")

        exporter = _make_exporter(tmp_path)
        exporter._clean_output(out)

        assert out.exists()
        assert list(out.iterdir()) == []

    def test_creates_nonexistent_directory(self, tmp_path: Path) -> None:
        out = tmp_path / "new_dist"
        assert not out.exists()

        exporter = _make_exporter(tmp_path)
        exporter._clean_output(out)

        assert out.is_dir()


# ---------------------------------------------------------------------------
# Content page export
# ---------------------------------------------------------------------------


class TestContentPageExport:
    """StaticExporter._render_content_pages — render Bengal pages to files."""

    def test_renders_pages_to_correct_paths(self, tmp_path: Path) -> None:
        from tests.conftest import make_test_page, make_test_site

        output = tmp_path / "dist"
        output.mkdir()

        pages = [
            make_test_page(tmp_path / "home.md", href="/", html_content="<p>Home</p>"),
            make_test_page(
                tmp_path / "about.md", href="/about/", html_content="<p>About</p>",
            ),
        ]
        site = make_test_site(tmp_path, pages)

        # Mock Kida template env on the Chirp app
        mock_template = MagicMock()
        mock_template.render.return_value = "<html>rendered</html>"
        mock_env = MagicMock()
        mock_env.get_template.return_value = mock_template

        app = MagicMock()
        app._kida_env = mock_env

        config = PurrConfig(root=tmp_path, output=output)
        exporter = StaticExporter(site=site, app=app, config=config)

        results = exporter._render_content_pages(output)

        assert len(results) == 2
        assert all(r.source_type == "content" for r in results)
        assert (output / "index.html").exists()
        assert (output / "about" / "index.html").exists()

    def test_skips_pages_without_permalink(self, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        output.mkdir()

        # Mock a page with no href and no _path
        page = MagicMock(spec=[])  # no attributes at all

        from tests.conftest import make_test_site

        site = make_test_site(tmp_path, [page])

        app = MagicMock()
        app._kida_env = MagicMock()

        config = PurrConfig(root=tmp_path, output=output)
        exporter = StaticExporter(site=site, app=app, config=config)

        results = exporter._render_content_pages(output)
        assert len(results) == 0

    def test_raises_export_error_on_render_failure(self, tmp_path: Path) -> None:
        from tests.conftest import make_test_page, make_test_site

        output = tmp_path / "dist"
        output.mkdir()

        pages = [make_test_page(tmp_path / "p.md", href="/p/")]
        site = make_test_site(tmp_path, pages)

        mock_env = MagicMock()
        mock_env.get_template.side_effect = RuntimeError("template not found")

        app = MagicMock()
        app._kida_env = mock_env

        config = PurrConfig(root=tmp_path, output=output)
        exporter = StaticExporter(site=site, app=app, config=config)

        with pytest.raises(ExportError, match="Failed to render content page"):
            exporter._render_content_pages(output)


# ---------------------------------------------------------------------------
# 404 page
# ---------------------------------------------------------------------------


class TestErrorPages:
    """StaticExporter._render_error_pages — 404 rendering."""

    def test_renders_404_when_template_exists(self, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        output.mkdir()

        mock_template = MagicMock()
        mock_template.render.return_value = "<html>404 Not Found</html>"
        mock_env = MagicMock()
        mock_env.get_template.return_value = mock_template

        app = MagicMock()
        app._kida_env = mock_env

        from tests.conftest import make_test_site

        site = make_test_site(tmp_path)
        config = PurrConfig(root=tmp_path, output=output)
        exporter = StaticExporter(site=site, app=app, config=config)

        results = exporter._render_error_pages(output)

        assert len(results) == 1
        assert results[0].source_type == "error_page"
        assert results[0].source_path == "/404.html"
        assert (output / "404.html").exists()

    def test_skips_when_no_404_template(self, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        output.mkdir()

        mock_env = MagicMock()
        mock_env.get_template.side_effect = FileNotFoundError("not found")

        app = MagicMock()
        app._kida_env = mock_env

        from tests.conftest import make_test_site

        site = make_test_site(tmp_path)
        config = PurrConfig(root=tmp_path, output=output)
        exporter = StaticExporter(site=site, app=app, config=config)

        results = exporter._render_error_pages(output)
        assert len(results) == 0

    def test_skips_when_no_kida_env(self, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        output.mkdir()

        app = MagicMock(spec=[])  # no _kida_env attribute

        from tests.conftest import make_test_site

        site = make_test_site(tmp_path)
        config = PurrConfig(root=tmp_path, output=output)
        exporter = StaticExporter(site=site, app=app, config=config)

        results = exporter._render_error_pages(output)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# _get_kida_env
# ---------------------------------------------------------------------------


class TestGetKidaEnv:
    """StaticExporter._get_kida_env — freezes app and retrieves env."""

    def test_calls_ensure_frozen(self, tmp_path: Path) -> None:
        app = MagicMock()
        mock_env = MagicMock()
        app._kida_env = mock_env

        exporter = _make_exporter(tmp_path, app=app)
        result = exporter._get_kida_env()

        app._ensure_frozen.assert_called_once()
        assert result is mock_env

    def test_raises_when_no_env(self, tmp_path: Path) -> None:
        app = MagicMock()
        app._kida_env = None
        app.kida_env = None
        app.template_env = None

        exporter = _make_exporter(tmp_path, app=app)
        with pytest.raises(ExportError, match="Cannot access Kida"):
            exporter._get_kida_env()


# ---------------------------------------------------------------------------
# _is_exportable
# ---------------------------------------------------------------------------


class TestIsExportable:
    """StaticExporter._is_exportable — route opt-out via exportable = False."""

    def test_defaults_to_true_for_unknown_module(self, tmp_path: Path) -> None:
        from purr.routes.loader import RouteDefinition

        defn = RouteDefinition(
            path="/missing",
            handler=lambda r: None,
            methods=("GET",),
            name="missing",
            source=tmp_path / "nonexistent.py",
            nav_title=None,
        )
        assert StaticExporter._is_exportable(defn) is True

    def test_respects_exportable_false(self, tmp_path: Path) -> None:
        import sys

        from purr.routes.loader import RouteDefinition

        # Create a fake module with exportable = False in sys.modules
        route_file = tmp_path / "not_exported.py"
        route_file.write_text("exportable = False")
        module_name = "purr_routes._test_not_exported"

        fake_module = type(sys)("fake_route")
        fake_module.__file__ = str(route_file)
        fake_module.exportable = False  # type: ignore[attr-defined]
        sys.modules[module_name] = fake_module

        try:
            defn = RouteDefinition(
                path="/hidden",
                handler=lambda r: None,
                methods=("GET",),
                name="hidden",
                source=route_file,
                nav_title=None,
            )
            assert StaticExporter._is_exportable(defn) is False
        finally:
            del sys.modules[module_name]

    def test_exportable_true_by_default_in_module(self, tmp_path: Path) -> None:
        import sys

        from purr.routes.loader import RouteDefinition

        route_file = tmp_path / "exported.py"
        route_file.write_text("# no exportable attr")
        module_name = "purr_routes._test_exported"

        fake_module = type(sys)("fake_route")
        fake_module.__file__ = str(route_file)
        sys.modules[module_name] = fake_module

        try:
            defn = RouteDefinition(
                path="/visible",
                handler=lambda r: None,
                methods=("GET",),
                name="visible",
                source=route_file,
                nav_title=None,
            )
            assert StaticExporter._is_exportable(defn) is True
        finally:
            del sys.modules[module_name]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_exporter(
    root: Path,
    *,
    app: object | None = None,
) -> StaticExporter:
    """Create a minimal StaticExporter for testing helper methods."""
    from tests.conftest import make_test_site

    site = make_test_site(root)
    if app is None:
        app = MagicMock()
    config = PurrConfig(root=root)
    return StaticExporter(site=site, app=app, config=config)
