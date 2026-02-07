"""Tests for purr.routes.loader — dynamic route discovery and loading."""

from pathlib import Path

import pytest

from purr._errors import ConfigError
from purr.routes.loader import (
    NavEntry,
    RouteDefinition,
    _derive_nav_title,
    _derive_path,
    build_nav_entries,
    discover_routes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def routes_dir(tmp_path: Path) -> Path:
    """Create a routes/ directory for testing."""
    d = tmp_path / "routes"
    d.mkdir()
    return d


def _write_route(routes_dir: Path, name: str, content: str) -> Path:
    """Write a route module and return its path."""
    p = routes_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# RouteDefinition dataclass
# ---------------------------------------------------------------------------


class TestRouteDefinition:
    """Verify RouteDefinition is frozen and well-behaved."""

    def test_frozen(self) -> None:
        defn = RouteDefinition(
            path="/search",
            handler=lambda: None,
            methods=("GET",),
            name="route:/search",
            source=Path("search.py"),
            nav_title="Search",
        )
        with pytest.raises(AttributeError):
            defn.path = "/other"  # type: ignore[misc]

    def test_equality(self) -> None:
        handler = lambda: None  # noqa: E731
        a = RouteDefinition(
            path="/a", handler=handler, methods=("GET",),
            name="r", source=Path("a.py"), nav_title=None,
        )
        b = RouteDefinition(
            path="/a", handler=handler, methods=("GET",),
            name="r", source=Path("a.py"), nav_title=None,
        )
        assert a == b


# ---------------------------------------------------------------------------
# NavEntry dataclass
# ---------------------------------------------------------------------------


class TestNavEntry:
    """Verify NavEntry is frozen and defaults."""

    def test_frozen(self) -> None:
        entry = NavEntry(path="/search", title="Search")
        with pytest.raises(AttributeError):
            entry.title = "Other"  # type: ignore[misc]

    def test_default_is_dynamic(self) -> None:
        entry = NavEntry(path="/search", title="Search")
        assert entry.is_dynamic is True


# ---------------------------------------------------------------------------
# _derive_path
# ---------------------------------------------------------------------------


class TestDerivePath:
    """Path derivation from file position relative to routes/ dir."""

    def test_simple_file(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "search.py", "")
        assert _derive_path(routes_dir / "search.py", routes_dir) == "/search"

    def test_nested_file(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "api/users.py", "")
        assert _derive_path(routes_dir / "api" / "users.py", routes_dir) == "/api/users"

    def test_deeply_nested(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "api/v1/items.py", "")
        assert _derive_path(
            routes_dir / "api" / "v1" / "items.py", routes_dir
        ) == "/api/v1/items"


# ---------------------------------------------------------------------------
# _derive_nav_title
# ---------------------------------------------------------------------------


class TestDeriveNavTitle:
    """Navigation title derivation from URL paths."""

    def test_simple(self) -> None:
        assert _derive_nav_title("/search") == "Search"

    def test_nested(self) -> None:
        assert _derive_nav_title("/api/users") == "Users"

    def test_hyphenated(self) -> None:
        assert _derive_nav_title("/getting-started") == "Getting Started"

    def test_underscored(self) -> None:
        assert _derive_nav_title("/my_page") == "My Page"


# ---------------------------------------------------------------------------
# discover_routes — discovery and loading
# ---------------------------------------------------------------------------


class TestDiscoverRoutes:
    """Unit tests for the route discovery pipeline."""

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        """Gracefully returns () when routes/ doesn't exist."""
        result = discover_routes(tmp_path / "nonexistent")
        assert result == ()

    def test_empty_directory_returns_empty(self, routes_dir: Path) -> None:
        """Gracefully returns () when routes/ exists but is empty."""
        result = discover_routes(routes_dir)
        assert result == ()

    def test_discovers_get_handler(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "search.py", (
            "async def get(request):\n"
            "    return 'search results'\n"
        ))
        defs = discover_routes(routes_dir)
        assert len(defs) == 1
        assert defs[0].path == "/search"
        assert defs[0].methods == ("GET",)
        assert defs[0].nav_title == "Search"

    def test_discovers_post_handler(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "submit.py", (
            "async def post(request):\n"
            "    return 'submitted'\n"
        ))
        defs = discover_routes(routes_dir)
        assert len(defs) == 1
        assert defs[0].methods == ("POST",)
        # POST handlers don't get nav titles
        assert defs[0].nav_title is None

    def test_discovers_multiple_methods(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "items.py", (
            "async def get(request):\n"
            "    return 'list items'\n"
            "\n"
            "async def post(request):\n"
            "    return 'create item'\n"
        ))
        defs = discover_routes(routes_dir)
        assert len(defs) == 2
        methods = {d.methods[0] for d in defs}
        assert methods == {"GET", "POST"}

    def test_handler_function_maps_to_get(self, routes_dir: Path) -> None:
        """A ``handler()`` function maps to GET when no explicit ``get`` exists."""
        _write_route(routes_dir, "search.py", (
            "async def handler(request):\n"
            "    return 'search'\n"
        ))
        defs = discover_routes(routes_dir)
        assert len(defs) == 1
        assert defs[0].methods == ("GET",)

    def test_handler_ignored_when_get_exists(self, routes_dir: Path) -> None:
        """``handler()`` is ignored if an explicit ``get()`` is also defined."""
        _write_route(routes_dir, "search.py", (
            "async def get(request):\n"
            "    return 'get search'\n"
            "\n"
            "async def handler(request):\n"
            "    return 'handler search'\n"
        ))
        defs = discover_routes(routes_dir)
        # Only the explicit get, not the handler
        get_defs = [d for d in defs if d.methods == ("GET",)]
        assert len(get_defs) == 1

    def test_explicit_path_override(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "dashboard.py", (
            "path = '/admin/dash'\n"
            "\n"
            "async def get(request):\n"
            "    return 'dashboard'\n"
        ))
        defs = discover_routes(routes_dir)
        assert defs[0].path == "/admin/dash"

    def test_explicit_name_override(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "search.py", (
            "name = 'site-search'\n"
            "\n"
            "async def get(request):\n"
            "    return 'search'\n"
        ))
        defs = discover_routes(routes_dir)
        assert "site-search" in defs[0].name

    def test_explicit_nav_title(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "search.py", (
            "nav_title = 'Site Search'\n"
            "\n"
            "async def get(request):\n"
            "    return 'search'\n"
        ))
        defs = discover_routes(routes_dir)
        assert defs[0].nav_title == "Site Search"

    def test_nested_route_discovery(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "api/users.py", (
            "async def get(request):\n"
            "    return 'users'\n"
        ))
        defs = discover_routes(routes_dir)
        assert len(defs) == 1
        assert defs[0].path == "/api/users"

    def test_skips_init_files(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "__init__.py", "# init")
        _write_route(routes_dir, "search.py", (
            "async def get(request):\n"
            "    return 'search'\n"
        ))
        defs = discover_routes(routes_dir)
        assert len(defs) == 1
        assert defs[0].path == "/search"

    def test_skips_private_files(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "_helpers.py", "def util(): pass")
        _write_route(routes_dir, "search.py", (
            "async def get(request):\n"
            "    return 'search'\n"
        ))
        defs = discover_routes(routes_dir)
        assert len(defs) == 1

    def test_duplicate_paths_raises(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "page_a.py", (
            "path = '/same'\n"
            "\n"
            "async def get(request):\n"
            "    return 'a'\n"
        ))
        _write_route(routes_dir, "page_b.py", (
            "path = '/same'\n"
            "\n"
            "async def get(request):\n"
            "    return 'b'\n"
        ))
        with pytest.raises(ConfigError, match="Duplicate route"):
            discover_routes(routes_dir)

    def test_sync_handler_raises(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "bad.py", (
            "def get(request):\n"
            "    return 'not async'\n"
        ))
        with pytest.raises(ConfigError, match="must be an async function"):
            discover_routes(routes_dir)

    def test_no_params_handler_raises(self, routes_dir: Path) -> None:
        _write_route(routes_dir, "bad.py", (
            "async def get():\n"
            "    return 'no params'\n"
        ))
        with pytest.raises(ConfigError, match="must accept at least one parameter"):
            discover_routes(routes_dir)

    def test_module_with_no_handlers_returns_empty(self, routes_dir: Path) -> None:
        """A module without any handler functions is silently skipped."""
        _write_route(routes_dir, "utils.py", (
            "CONSTANT = 42\n"
            "\n"
            "def helper():\n"
            "    pass\n"
        ))
        defs = discover_routes(routes_dir)
        assert defs == ()

    def test_source_path_recorded(self, routes_dir: Path) -> None:
        py_file = _write_route(routes_dir, "search.py", (
            "async def get(request):\n"
            "    return 'search'\n"
        ))
        defs = discover_routes(routes_dir)
        assert defs[0].source == py_file


# ---------------------------------------------------------------------------
# build_nav_entries
# ---------------------------------------------------------------------------


class TestBuildNavEntries:
    """Tests for building navigation entries from route definitions."""

    def test_empty_input(self) -> None:
        assert build_nav_entries(()) == ()

    def test_single_get_route(self) -> None:
        defn = RouteDefinition(
            path="/search", handler=lambda: None, methods=("GET",),
            name="r", source=Path("s.py"), nav_title="Search",
        )
        entries = build_nav_entries((defn,))
        assert len(entries) == 1
        assert entries[0].path == "/search"
        assert entries[0].title == "Search"
        assert entries[0].is_dynamic is True

    def test_excludes_routes_without_nav_title(self) -> None:
        defn = RouteDefinition(
            path="/api/data", handler=lambda: None, methods=("POST",),
            name="r", source=Path("s.py"), nav_title=None,
        )
        entries = build_nav_entries((defn,))
        assert entries == ()

    def test_deduplicates_by_path(self) -> None:
        handler = lambda: None  # noqa: E731
        defs = (
            RouteDefinition(
                path="/items", handler=handler, methods=("GET",),
                name="r:GET", source=Path("s.py"), nav_title="Items",
            ),
            RouteDefinition(
                path="/items", handler=handler, methods=("POST",),
                name="r:POST", source=Path("s.py"), nav_title=None,
            ),
        )
        entries = build_nav_entries(defs)
        assert len(entries) == 1

    def test_sorted_by_path(self) -> None:
        handler = lambda: None  # noqa: E731
        defs = (
            RouteDefinition(
                path="/zebra", handler=handler, methods=("GET",),
                name="r", source=Path("z.py"), nav_title="Zebra",
            ),
            RouteDefinition(
                path="/alpha", handler=handler, methods=("GET",),
                name="r", source=Path("a.py"), nav_title="Alpha",
            ),
        )
        entries = build_nav_entries(defs)
        assert entries[0].path == "/alpha"
        assert entries[1].path == "/zebra"
