"""Tests for purr.content.watcher — file change detection and categorization."""

from __future__ import annotations

from pathlib import Path

import pytest

from purr.config import PurrConfig
from purr.content.watcher import ChangeEvent, categorize_change


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config(tmp_path: Path) -> PurrConfig:
    """A PurrConfig rooted at a temp directory."""
    return PurrConfig(root=tmp_path)


# ---------------------------------------------------------------------------
# ChangeEvent dataclass tests
# ---------------------------------------------------------------------------


class TestChangeEvent:
    """Verify ChangeEvent is frozen and well-behaved."""

    def test_frozen(self) -> None:
        event = ChangeEvent(
            path=Path("/tmp/test.md"), kind="modified", category="content"
        )
        with pytest.raises(AttributeError):
            event.kind = "created"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = ChangeEvent(path=Path("/a.md"), kind="modified", category="content")
        b = ChangeEvent(path=Path("/a.md"), kind="modified", category="content")
        assert a == b

    def test_hashable(self) -> None:
        event = ChangeEvent(path=Path("/a.md"), kind="created", category="template")
        assert isinstance(hash(event), int)


# ---------------------------------------------------------------------------
# categorize_change tests
# ---------------------------------------------------------------------------


class TestCategorizeChange:
    """Unit tests for categorize_change()."""

    def test_content_markdown(self, config: PurrConfig) -> None:
        path = config.root / "content" / "docs" / "page.md"
        assert categorize_change(path, config) == "content"

    def test_content_nested(self, config: PurrConfig) -> None:
        path = config.root / "content" / "deep" / "nested" / "file.md"
        assert categorize_change(path, config) == "content"

    def test_template_html(self, config: PurrConfig) -> None:
        path = config.root / "templates" / "page.html"
        assert categorize_change(path, config) == "template"

    def test_template_nested(self, config: PurrConfig) -> None:
        path = config.root / "templates" / "partials" / "nav.html"
        assert categorize_change(path, config) == "template"

    def test_static_asset(self, config: PurrConfig) -> None:
        path = config.root / "static" / "style.css"
        assert categorize_change(path, config) == "asset"

    def test_route_file(self, config: PurrConfig) -> None:
        path = config.root / "routes" / "search.py"
        assert categorize_change(path, config) == "route"

    def test_config_yaml(self, config: PurrConfig) -> None:
        path = config.root / "purr.yaml"
        assert categorize_change(path, config) == "config"

    def test_config_yml(self, config: PurrConfig) -> None:
        path = config.root / "purr.yml"
        assert categorize_change(path, config) == "config"

    def test_config_toml(self, config: PurrConfig) -> None:
        path = config.root / "purr.toml"
        assert categorize_change(path, config) == "config"

    def test_unknown_file_returns_none(self, config: PurrConfig) -> None:
        path = config.root / "random" / "file.txt"
        assert categorize_change(path, config) is None

    def test_file_outside_root_returns_none(self, config: PurrConfig) -> None:
        path = Path("/completely/elsewhere/file.md")
        assert categorize_change(path, config) is None

    def test_root_file_not_config(self, config: PurrConfig) -> None:
        """A root-level file that isn't a known config name -> None."""
        path = config.root / "README.md"
        assert categorize_change(path, config) is None

    def test_custom_content_dir(self, tmp_path: Path) -> None:
        """Respects PurrConfig.content_dir override."""
        config = PurrConfig(root=tmp_path, content_dir="docs")
        path = tmp_path / "docs" / "page.md"
        assert categorize_change(path, config) == "content"

    def test_custom_templates_dir(self, tmp_path: Path) -> None:
        """Respects PurrConfig.templates_dir override."""
        config = PurrConfig(root=tmp_path, templates_dir="layouts")
        path = tmp_path / "layouts" / "base.html"
        assert categorize_change(path, config) == "template"
