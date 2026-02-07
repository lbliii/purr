"""Dynamic route discovery and loading.

Scans a ``routes/`` directory for Python modules, imports them, and extracts
route definitions using file-path convention with optional explicit overrides.

Public API::

    from purr.routes import discover_routes, build_nav_entries

    definitions = discover_routes(Path("my-site/routes"))
    nav_entries = build_nav_entries(definitions)
"""

from purr.routes.loader import NavEntry, RouteDefinition, build_nav_entries, discover_routes

__all__ = [
    "NavEntry",
    "RouteDefinition",
    "build_nav_entries",
    "discover_routes",
]
