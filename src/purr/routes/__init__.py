"""Dynamic route discovery and loading.

Scans a ``routes/`` directory for Python modules, imports them, and extracts
route definitions using file-path convention with optional explicit overrides.

Public API::

    from purr.routes import discover_routes

    definitions = discover_routes(Path("my-site/routes"))
"""

from purr.routes.loader import RouteDefinition, discover_routes

__all__ = [
    "RouteDefinition",
    "discover_routes",
]
