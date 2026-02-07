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

Part of the Bengal ecosystem:

    purr        Content runtime   (connects everything)
    pounce      ASGI server       (serves apps)
    chirp       Web framework     (serves HTML)
    kida        Template engine   (renders HTML)
    patitas     Markdown parser   (parses content)
    rosettes    Syntax highlighter (highlights code)
    bengal      Static site gen   (builds sites)

"""

# PEP 703: Declare this module as free-threading safe
_Py_mod_gil = 0

__version__ = "0.1.0-dev"
__all__ = [
    "PurrConfig",
    "__version__",
    "build",
    "dev",
    "serve",
]


def __getattr__(name: str) -> object:
    """Lazy imports for public API.

    Keeps ``import purr`` fast while providing a clean top-level API.
    """
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
