"""Purr application — the unified Bengal + Chirp integration.

PurrApp wraps a Bengal Site and a Chirp App into a single content-reactive application.
The three public functions (dev, build, serve) are the primary entry points.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from purr._errors import ConfigError, ContentError
from purr.config import PurrConfig

if TYPE_CHECKING:
    from bengal.core.site import Site
    from chirp import App


def _load_site(root: Path) -> Site:
    """Load a Bengal site from the given root directory.

    Raises:
        ConfigError: If the site cannot be loaded (missing config, bad structure).

    """
    try:
        from bengal.core.site import Site

        return Site.from_config(root)
    except Exception as exc:
        msg = f"Failed to load Bengal site from {root}: {exc}"
        raise ConfigError(msg) from exc


def _create_chirp_app(config: PurrConfig, *, debug: bool = False) -> App:
    """Create a Chirp App configured for the Purr site.

    Sets up the Kida template engine with the site's template directory
    and configures static file serving.

    """
    from chirp import App, AppConfig

    app_config = AppConfig(
        template_dir=config.templates_path,
        debug=debug,
        host=config.host,
        port=config.port,
    )
    return App(config=app_config)


def _wire_content_routes(site: Site, app: App) -> int:
    """Register Bengal content pages as Chirp routes.

    Returns the number of pages registered.

    Raises:
        ContentError: If route registration fails.

    """
    from purr.content.router import ContentRouter

    try:
        router = ContentRouter(site, app)
        router.register_pages()
        return router.page_count
    except Exception as exc:
        msg = f"Failed to register content routes: {exc}"
        raise ContentError(msg) from exc


def _mount_static_files(app: App, config: PurrConfig) -> None:
    """Mount static file middleware if the static directory exists."""
    if config.static_path.is_dir():
        from chirp.middleware import StaticFiles

        app.add_middleware(StaticFiles(directory=config.static_path, prefix="/static"))


def _print_banner(config: PurrConfig, page_count: int, mode: str) -> None:
    """Print the Purr startup banner to stderr."""
    from purr import __version__

    lines = [
        f"Purr v{__version__} — content-reactive runtime",
        "─" * 41,
        f"  Loaded {page_count} page{'s' if page_count != 1 else ''}",
        f"  Templates: {config.templates_path}",
    ]

    if mode == "dev":
        lines.append(f"\n  http://{config.host}:{config.port}")
        lines.append("\n  Watching for changes...")
    elif mode == "serve":
        workers_label = config.workers if config.workers > 0 else "auto"
        lines.append(f"  Workers: {workers_label}")
        lines.append(f"\n  http://{config.host}:{config.port}")
    elif mode == "build":
        lines.append(f"  Output: {config.output_path}")

    print("\n".join(lines), file=sys.stderr)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def dev(root: str | Path = ".", **kwargs: object) -> None:
    """Start a content-reactive development server.

    Launches a Pounce server with single-worker mode. Content changes are
    served on page refresh (Phase 2 will add SSE for live updates).

    Args:
        root: Path to the site root directory.
        **kwargs: Override PurrConfig fields.

    """
    config = PurrConfig(root=Path(root), **kwargs)

    # Load Bengal site
    site = _load_site(config.root)

    # Create Chirp app with debug enabled
    app = _create_chirp_app(config, debug=True)

    # Wire content routes
    page_count = _wire_content_routes(site, app)

    # Mount static files
    _mount_static_files(app, config)

    # Banner
    _print_banner(config, page_count, mode="dev")

    # Run via Pounce (single worker, dev mode)
    app.run(host=config.host, port=config.port)


def build(root: str | Path = ".", **kwargs: object) -> None:
    """Export the site as static HTML files.

    Delegates to Bengal's BuildOrchestrator for the full static build pipeline.
    Output is deployable to any static hosting (CDN, GitHub Pages, S3, etc.).

    Args:
        root: Path to the site root directory.
        **kwargs: Override PurrConfig fields.

    """
    config = PurrConfig(root=Path(root), **kwargs)

    # Load Bengal site
    site = _load_site(config.root)

    # Banner
    _print_banner(config, len(site.pages), mode="build")

    # Delegate to Bengal's build pipeline
    from bengal.orchestration.build import BuildOrchestrator
    from bengal.orchestration.build.options import BuildOptions

    orchestrator = BuildOrchestrator(site)
    orchestrator.build(BuildOptions())


def serve(root: str | Path = ".", **kwargs: object) -> None:
    """Run the site as a live Pounce server in production.

    Static content is served via Chirp routes. Dynamic routes (Phase 3)
    will be handled per-request. Multiple Pounce workers share the frozen
    Chirp app and immutable Bengal site data.

    Args:
        root: Path to the site root directory.
        **kwargs: Override PurrConfig fields.

    """
    config = PurrConfig(root=Path(root), **kwargs)

    # Load Bengal site
    site = _load_site(config.root)

    # Create Chirp app (production mode — no debug, no reload)
    app = _create_chirp_app(config, debug=False)

    # Wire content routes
    page_count = _wire_content_routes(site, app)

    # Mount static files
    _mount_static_files(app, config)

    # Banner
    _print_banner(config, page_count, mode="serve")

    # Run via Pounce directly with multi-worker support
    from pounce.config import ServerConfig
    from pounce.server import Server

    server_config = ServerConfig(
        host=config.host,
        port=config.port,
        workers=config.workers,  # 0 = auto-detect via Pounce
    )
    server = Server(server_config, app)
    server.run()
