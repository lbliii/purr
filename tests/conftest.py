"""Shared test fixtures for purr."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_site(tmp_path: Path) -> Path:
    """Create a minimal site structure for testing.

    Returns the path to the site root with content/, templates/, and static/ dirs.
    """
    content = tmp_path / "content"
    content.mkdir()
    (content / "_index.md").write_text(
        "---\ntitle: Home\n---\n\n# Welcome\n\nThis is the home page.\n"
    )

    docs = content / "docs"
    docs.mkdir()
    (docs / "getting-started.md").write_text(
        "---\ntitle: Getting Started\n---\n\n# Getting Started\n\nHello world.\n"
    )

    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "page.html").write_text(
        "<!DOCTYPE html>\n<html>\n<body>{{ page.body }}</body>\n</html>\n"
    )

    static = tmp_path / "static"
    static.mkdir()

    return tmp_path


@pytest.fixture
def site_with_routes(tmp_site: Path) -> Path:
    """Extend tmp_site with a routes/ directory for dynamic route testing."""
    routes = tmp_site / "routes"
    routes.mkdir()
    (routes / "__init__.py").write_text("")
    (routes / "search.py").write_text(
        'async def search(request):\n    return "search results"\n'
    )
    return tmp_site
