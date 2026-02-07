"""Shared test fixtures for purr."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def tmp_site(tmp_path: Path) -> Path:
    """Create a minimal site structure for testing.

    Returns the path to the site root with content/, templates/, and static/ dirs.
    The structure is compatible with Bengal's ``Site.for_testing()`` factory.
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
        "<!DOCTYPE html>\n<html>\n<body>{{ content }}</body>\n</html>\n"
    )
    (templates / "index.html").write_text(
        "<!DOCTYPE html>\n<html>\n<body>{{ content }}</body>\n</html>\n"
    )

    static = tmp_path / "static"
    static.mkdir()
    (static / "style.css").write_text("body { margin: 0; }\n")

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


def make_test_page(
    source_path: Path,
    *,
    href: str,
    title: str = "Test Page",
    html_content: str = "<p>Test content</p>",
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Create a minimal Bengal Page for unit testing.

    Sets ``href`` directly on the page's ``__dict__`` to bypass the property's
    computed resolution (which requires a fully wired Site).  This is the same
    pattern Bengal's own test suite uses.
    """
    from bengal.core.page import Page

    raw_metadata = metadata or {"title": title}
    page = Page(source_path=source_path, _raw_metadata=raw_metadata, html_content=html_content)
    # Set href directly for testing (Bengal's tests use this pattern)
    page.__dict__["href"] = href
    return page


def make_test_site(
    root_path: Path,
    pages: list[Any] | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> Any:
    """Create a minimal Bengal Site for unit testing.

    Uses ``Site.for_testing()`` and optionally populates ``site.pages``.
    """
    from bengal.core.site import Site

    site = Site.for_testing(root_path=root_path, config=config)
    if pages:
        site.pages = pages
    return site
