"""Purr — A content-reactive runtime for Python 3.14t.

Unifies the Bengal ecosystem into a single content-reactive runtime. Edit content,
see the browser update surgically. Add dynamic routes alongside static pages.
Deploy as static files or run as a live server.

Quick start::

    import purr

    purr.dev("my-site/")

Three modes::

    purr.dev("my-site/")          # Reactive local development
    purr.build("my-site/")        # Static export
    purr.serve("my-site/")        # Live production server

Site accessor (available after ``dev()`` or ``serve()`` initializes)::

    from purr import site
    results = site.search(query)

Part of the Bengal ecosystem:

    purr        Content runtime   (connects everything)
    pounce      ASGI server       (serves apps)
    chirp       Web framework     (serves HTML)
    kida        Template engine   (renders HTML)
    patitas     Markdown parser   (parses content)
    rosettes    Syntax highlighter (highlights code)
    bengal      Static site gen   (builds sites)

"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bengal.core.site import Site

# PEP 703: Declare this module as free-threading safe
_Py_mod_gil = 0

__version__ = "0.1.0-dev"
__all__ = [
    "PurrConfig",
    "__version__",
    "build",
    "dev",
    "serve",
    "site",
]

# ---------------------------------------------------------------------------
# Site accessor — set once at startup, immutable thereafter
# ---------------------------------------------------------------------------

_site_ref: Site | None = None


def _set_site(site_instance: Site) -> None:
    """Store the Bengal Site for access by dynamic route handlers.

    Called once during ``dev()`` or ``serve()`` initialization.  The Site
    object is frozen/immutable, so a module-level reference is safe for
    free-threading.

    Args:
        site_instance: The loaded Bengal Site.

    """
    global _site_ref  # noqa: PLW0603
    _site_ref = site_instance


def __getattr__(name: str) -> object:
    """Lazy imports and site accessor for public API.

    Keeps ``import purr`` fast while providing a clean top-level API.
    The ``site`` attribute is a runtime reference set during initialization.
    """
    if name == "site":
        if _site_ref is None:
            msg = (
                "purr.site accessed before initialization. "
                "Call purr.dev() or purr.serve() first."
            )
            raise RuntimeError(msg)
        return _site_ref

    if name == "PurrConfig":
        from purr.config import PurrConfig

        return PurrConfig

    if name == "dev":
        from purr.app import dev

        return dev

    if name == "build":
        from purr.app import build

        return build

    if name == "serve":
        from purr.app import serve

        return serve

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
