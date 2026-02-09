"""Tests for purr.config."""

from pathlib import Path

from purr.config import PurrConfig


class TestPurrConfig:
    """PurrConfig — frozen dataclass with sensible defaults."""

    def test_defaults(self) -> None:
        config = PurrConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 3000
        assert config.workers == 0
        assert config.content_dir == "content"
        assert config.templates_dir == "templates"
        assert config.static_dir == "static"
        assert config.routes_dir == "routes"

    def test_frozen(self) -> None:
        config = PurrConfig()
        with __import__("pytest").raises(AttributeError):
            config.port = 8000  # type: ignore[misc]

    def test_paths_resolve_from_root(self, tmp_path: Path) -> None:
        config = PurrConfig(root=tmp_path)
        assert config.content_path == tmp_path / "content"
        assert config.templates_path == tmp_path / "templates"
        assert config.static_path == tmp_path / "static"
        assert config.routes_path == tmp_path / "routes"
        assert config.output_path == tmp_path / "dist"

    def test_absolute_output_preserved(self, tmp_path: Path) -> None:
        output = Path("/tmp/custom-output")
        config = PurrConfig(root=tmp_path, output=output)
        assert config.output_path == output

    def test_custom_dirs(self, tmp_path: Path) -> None:
        config = PurrConfig(
            root=tmp_path,
            content_dir="pages",
            templates_dir="layouts",
            static_dir="assets",
        )
        assert config.content_path == tmp_path / "pages"
        assert config.templates_path == tmp_path / "layouts"
        assert config.static_path == tmp_path / "assets"

    def test_base_url_default_empty(self) -> None:
        config = PurrConfig()
        assert config.base_url == ""

    def test_base_url_custom(self) -> None:
        config = PurrConfig(base_url="https://example.com")
        assert config.base_url == "https://example.com"

    def test_fingerprint_default_false(self) -> None:
        config = PurrConfig()
        assert config.fingerprint is False

    def test_fingerprint_enabled(self) -> None:
        config = PurrConfig(fingerprint=True)
        assert config.fingerprint is True

    def test_relative_root_resolved_to_absolute(self) -> None:
        """Relative root is resolved to absolute in __post_init__."""
        config = PurrConfig(root=Path("site"))
        assert config.root.is_absolute()

    def test_absolute_root_unchanged(self, tmp_path: Path) -> None:
        """Absolute root is not modified by __post_init__."""
        config = PurrConfig(root=tmp_path)
        assert config.root == tmp_path
