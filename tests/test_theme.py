"""Tests for purr.theme — default theme and fallback chain."""

from __future__ import annotations

from pathlib import Path

from purr.config import PurrConfig
from purr.theme import _bundled_theme_path, get_asset_dirs, get_template_dirs


# ---------------------------------------------------------------------------
# Bundled theme structure
# ---------------------------------------------------------------------------


class TestBundledTheme:
    """Verify the bundled default theme has all required files."""

    def test_bundled_path_exists(self) -> None:
        path = _bundled_theme_path()
        assert path.is_dir(), f"Bundled theme not found at {path}"

    def test_templates_directory_exists(self) -> None:
        path = _bundled_theme_path() / "templates"
        assert path.is_dir()

    def test_required_templates_present(self) -> None:
        templates = _bundled_theme_path() / "templates"
        for name in ("base.html", "page.html", "index.html", "404.html"):
            assert (templates / name).is_file(), f"Missing template: {name}"

    def test_assets_directory_exists(self) -> None:
        path = _bundled_theme_path() / "assets"
        assert path.is_dir()

    def test_css_files_present(self) -> None:
        css = _bundled_theme_path() / "assets" / "css"
        assert (css / "purr.css").is_file()
        assert (css / "tokens.css").is_file()

    def test_js_files_present(self) -> None:
        js = _bundled_theme_path() / "assets" / "js"
        assert (js / "purr.js").is_file()

    def test_base_template_contains_block_content(self) -> None:
        base = _bundled_theme_path() / "templates" / "base.html"
        content = base.read_text(encoding="utf-8")
        assert "{% block content %}" in content

    def test_page_template_extends_base(self) -> None:
        page = _bundled_theme_path() / "templates" / "page.html"
        content = page.read_text(encoding="utf-8")
        assert '{% extends "base.html" %}' in content

    def test_tokens_css_has_purr_primary(self) -> None:
        tokens = _bundled_theme_path() / "assets" / "css" / "tokens.css"
        content = tokens.read_text(encoding="utf-8")
        assert "--purr-primary" in content
        assert "#FF9D00" in content

    def test_purr_css_imports_tokens(self) -> None:
        purr_css = _bundled_theme_path() / "assets" / "css" / "purr.css"
        content = purr_css.read_text(encoding="utf-8")
        assert "tokens.css" in content
        assert "@layer" in content


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------


class TestFallbackChain:
    """Tests for template and asset directory resolution."""

    def test_user_templates_first(self, tmp_path: Path) -> None:
        config = PurrConfig(root=tmp_path)
        dirs = get_template_dirs(config)

        # User dir should come first
        assert dirs[0] == tmp_path / "templates"
        # Bundled should be second
        assert dirs[1] == _bundled_theme_path() / "templates"

    def test_user_assets_first(self, tmp_path: Path) -> None:
        config = PurrConfig(root=tmp_path)
        dirs = get_asset_dirs(config)

        assert dirs[0] == tmp_path / "static"
        assert dirs[1] == _bundled_theme_path() / "assets"

    def test_bundled_always_included(self, tmp_path: Path) -> None:
        """Even if user dir doesn't exist, bundled is still in the list."""
        config = PurrConfig(root=tmp_path)
        dirs = get_template_dirs(config)

        # User dir might not exist, but bundled should always be there
        bundled = _bundled_theme_path() / "templates"
        assert bundled in dirs
        assert bundled.is_dir()

    def test_custom_templates_dir(self, tmp_path: Path) -> None:
        config = PurrConfig(root=tmp_path, templates_dir="my_templates")
        dirs = get_template_dirs(config)

        assert dirs[0] == tmp_path / "my_templates"
        assert dirs[1] == _bundled_theme_path() / "templates"

    def test_custom_static_dir(self, tmp_path: Path) -> None:
        config = PurrConfig(root=tmp_path, static_dir="assets")
        dirs = get_asset_dirs(config)

        assert dirs[0] == tmp_path / "assets"
        assert dirs[1] == _bundled_theme_path() / "assets"

    def test_no_duplicate_when_pointing_to_bundled(self) -> None:
        """If user templates_dir somehow points to the bundled dir, no dup."""
        bundled = _bundled_theme_path() / "templates"
        config = PurrConfig(root=bundled.parent, templates_dir="templates")
        dirs = get_template_dirs(config)

        assert len(dirs) == 1
        assert dirs[0] == bundled
