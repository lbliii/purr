"""Route loader — discover and import user-defined Chirp routes.

Scans a ``routes/`` directory for Python modules and extracts route
definitions using a file-path convention:

    routes/search.py         -> GET /search
    routes/api/users.py      -> GET /api/users
    routes/dashboard.py      -> path = "/admin/dash"  (explicit override)

Handler convention — function names map to HTTP methods::

    async def get(request):   # GET
    async def post(request):  # POST
    async def handler(request):  # GET (catch-all default)

Modules may export optional metadata:

    path: str         — override URL path (default: derived from file path)
    name: str         — route name for URL generation
    nav_title: str    — title for navigation entries (default: derived from path)
"""

import importlib.util
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path

from purr._errors import ConfigError

# HTTP methods recognised as handler function names
_METHOD_NAMES: frozenset[str] = frozenset({
    "get",
    "post",
    "put",
    "delete",
    "patch",
})

# Catch-all handler name (maps to GET)
_HANDLER_NAME = "handler"


@dataclass(frozen=True, slots=True)
class RouteDefinition:
    """A single discovered route ready for Chirp registration.

    Attributes:
        path: URL path (e.g., ``/search``, ``/api/users/{id}``).
        handler: Async callable accepting a Chirp ``Request``.
        methods: HTTP methods this handler responds to (e.g., ``("GET",)``).
        name: Route name for URL generation and debugging.
        source: Filesystem path to the originating ``.py`` file.
        nav_title: Human-readable title for navigation entries, or *None*
            if the route should not appear in navigation.

    """

    path: str
    handler: object
    methods: tuple[str, ...]
    name: str
    source: Path
    nav_title: str | None


def discover_routes(routes_dir: Path) -> tuple[RouteDefinition, ...]:
    """Scan *routes_dir* for Python modules and return route definitions.

    Skips ``__init__.py``, ``__pycache__`` directories, and files whose names
    start with ``_``.  Returns an empty tuple when *routes_dir* does not exist
    or contains no loadable modules.

    Raises:
        ConfigError: On duplicate URL paths or invalid handler signatures.

    """
    if not routes_dir.is_dir():
        return ()

    definitions: list[RouteDefinition] = []
    seen_paths: dict[str, Path] = {}

    for py_file in sorted(routes_dir.rglob("*.py")):
        # Skip private files, __init__, and __pycache__ contents
        if py_file.name.startswith("_"):
            continue
        if "__pycache__" in py_file.parts:
            continue

        module = _load_module(py_file, routes_dir)
        if module is None:
            continue

        file_defs = _extract_definitions(module, py_file, routes_dir)
        for defn in file_defs:
            if defn.path in seen_paths:
                msg = (
                    f"Duplicate route path {defn.path!r}: "
                    f"defined in {seen_paths[defn.path]} and {py_file}"
                )
                raise ConfigError(msg)
            seen_paths[defn.path] = py_file
            definitions.append(defn)

    return tuple(definitions)


def _load_module(py_file: Path, routes_dir: Path) -> object | None:
    """Import a Python file as a module without touching ``sys.path``.

    Uses ``importlib.util.spec_from_file_location`` for safe, isolated loading.
    Returns *None* if the module cannot be loaded (logs nothing — the caller
    decides how to handle missing modules).

    """
    # Build a dotted module name: routes/api/users.py -> purr_routes.api.users
    relative = py_file.relative_to(routes_dir)
    parts = list(relative.with_suffix("").parts)
    module_name = "purr_routes." + ".".join(parts)

    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        return None

    try:
        module = importlib.util.module_from_spec(spec)
        # Register in sys.modules so relative imports within route files work
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        msg = f"Failed to load route module {py_file}: {exc}"
        raise ConfigError(msg) from exc

    return module


def _derive_path(py_file: Path, routes_dir: Path) -> str:
    """Derive a URL path from a file's position relative to *routes_dir*.

    ``routes/search.py``       -> ``/search``
    ``routes/api/users.py``    -> ``/api/users``
    ``routes/api/v1/items.py`` -> ``/api/v1/items``

    """
    relative = py_file.relative_to(routes_dir).with_suffix("")
    return "/" + "/".join(relative.parts)


def _derive_nav_title(path: str) -> str:
    """Derive a human-readable title from a URL path.

    ``/search``     -> ``Search``
    ``/api/users``  -> ``Users``

    """
    last_segment = path.rstrip("/").rsplit("/", maxsplit=1)[-1]
    return last_segment.replace("-", " ").replace("_", " ").title()


def _extract_definitions(
    module: object,
    py_file: Path,
    routes_dir: Path,
) -> list[RouteDefinition]:
    """Extract route definitions from a loaded module.

    Looks for handler functions named ``get``, ``post``, ``put``, ``delete``,
    ``patch``, or the catch-all ``handler`` (which maps to GET).

    """
    # Resolve path: explicit module-level ``path`` or derive from file
    path = getattr(module, "path", None)
    if path is None:
        path = _derive_path(py_file, routes_dir)
    elif not isinstance(path, str):
        msg = f"Route module {py_file}: 'path' must be a str, got {type(path).__name__}"
        raise ConfigError(msg)

    if not path.startswith("/"):
        path = "/" + path

    # Resolve optional metadata
    route_name = getattr(module, "name", None)
    if route_name is None:
        route_name = "route:" + path

    nav_title = getattr(module, "nav_title", None)
    if nav_title is None:
        nav_title = _derive_nav_title(path)

    # Discover handler functions
    definitions: list[RouteDefinition] = []

    for method_name in sorted(_METHOD_NAMES):
        func = getattr(module, method_name, None)
        if func is not None and callable(func):
            _validate_handler(func, method_name, py_file)
            definitions.append(RouteDefinition(
                path=path,
                handler=func,
                methods=(method_name.upper(),),
                name=f"{route_name}:{method_name.upper()}",
                source=py_file,
                nav_title=nav_title if method_name == "get" else None,
            ))

    # Catch-all ``handler`` (maps to GET) — only if no explicit ``get``
    handler_func = getattr(module, _HANDLER_NAME, None)
    if handler_func is not None and callable(handler_func):
        has_get = any(d.methods == ("GET",) for d in definitions)
        if not has_get:
            _validate_handler(handler_func, _HANDLER_NAME, py_file)
            definitions.append(RouteDefinition(
                path=path,
                handler=handler_func,
                methods=("GET",),
                name=route_name,
                source=py_file,
                nav_title=nav_title,
            ))

    return definitions


def _validate_handler(func: object, name: str, source: Path) -> None:
    """Validate that a handler is async and accepts at least one parameter.

    Raises:
        ConfigError: If the handler is not async or has no parameters.

    """
    if not inspect.iscoroutinefunction(func):
        msg = (
            f"Route handler '{name}' in {source} must be an async function "
            f"(use 'async def {name}(request)')."
        )
        raise ConfigError(msg)

    sig = inspect.signature(func)  # type: ignore[arg-type]
    if len(sig.parameters) < 1:
        msg = (
            f"Route handler '{name}' in {source} must accept at least one "
            f"parameter (the Chirp Request object)."
        )
        raise ConfigError(msg)
