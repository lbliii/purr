"""Purr application — the unified Bengal + Chirp integration.

PurrApp wraps a Bengal Site and a Chirp App into a single content-reactive application.
The three public functions (dev, build, serve) are the primary entry points.
"""

import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from purr._errors import ConfigError, ContentError
from purr.config import PurrConfig

if TYPE_CHECKING:
    from bengal.core.site import Site
    from chirp import App

    from purr.content.router import ContentRouter
    from purr.reactive.broadcaster import Broadcaster
    from purr.routes.loader import RouteDefinition


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

    Uses the theme fallback chain: user templates take priority, bundled
    default theme fills the gaps.  Template directories are resolved via
    ``purr.theme.get_template_dirs()``.

    Chirp's ``AppConfig.template_dir`` only accepts a single path, so we
    patch ``create_environment`` to construct a Kida ``FileSystemLoader``
    with multiple paths (which Kida natively supports).

    """
    from chirp import App, AppConfig

    from purr.theme import get_template_dirs

    template_dirs = get_template_dirs(config)

    # Pass the first dir to AppConfig (Chirp expects str | Path).
    app_config = AppConfig(
        template_dir=template_dirs[0],
        debug=debug,
        host=config.host,
        port=config.port,
    )

    # Patch Chirp's env creation to use Kida's multi-path loader.
    # Kida's FileSystemLoader natively supports a list of paths, but
    # Chirp's create_environment() stringifies the single path.
    # The patch captures template_dirs in its closure and persists until
    # App._freeze() is called (lazily on first request).
    import chirp.templating.integration as _tmpl

    def _create_env_multi(
        cfg: object, filters: dict, globals_: dict,
    ) -> object:
        from kida import Environment, FileSystemLoader

        env = Environment(
            loader=FileSystemLoader(template_dirs),
            autoescape=cfg.autoescape,  # type: ignore[attr-defined]
            auto_reload=cfg.debug,  # type: ignore[attr-defined]
            trim_blocks=cfg.trim_blocks,  # type: ignore[attr-defined]
            lstrip_blocks=cfg.lstrip_blocks,  # type: ignore[attr-defined]
        )
        if filters:
            env.update_filters(filters)
        for name, value in globals_.items():
            env.add_global(name, value)
        return env

    _tmpl.create_environment = _create_env_multi  # type: ignore[assignment]

    return App(config=app_config)


def _wire_content_routes(site: Site, app: App) -> tuple[ContentRouter, int]:
    """Register Bengal content pages as Chirp routes.

    Returns the ContentRouter instance and the number of pages registered.

    Raises:
        ContentError: If route registration fails.

    """
    from purr.content.router import ContentRouter

    try:
        router = ContentRouter(site, app)
        router.register_pages()
        return router, router.page_count
    except Exception as exc:
        msg = f"Failed to register content routes: {exc}"
        raise ContentError(msg) from exc


def _mount_static_files(app: App, config: PurrConfig) -> None:
    """Mount static file middleware with theme fallback.

    Mounts user static directory first, then the bundled theme assets.
    Both are served under ``/static``.  User files take precedence because
    Chirp's middleware stack is checked in registration order.

    """
    from chirp.middleware import StaticFiles

    from purr.theme import get_asset_dirs

    for asset_dir in get_asset_dirs(config):
        if asset_dir.is_dir():
            app.add_middleware(StaticFiles(directory=asset_dir, prefix="/static"))


def _wire_dynamic_routes(
    app: App,
    config: PurrConfig,
) -> tuple[RouteDefinition, ...]:
    """Discover and register user-defined routes from the ``routes/`` directory.

    Scans ``config.routes_path`` for Python modules, extracts handler functions,
    and registers each as a Chirp route.  Also injects navigation entries into
    Chirp's template globals so templates can render nav links for dynamic routes.

    Returns an empty tuple if the routes directory does not exist.

    """
    from purr.routes.loader import build_nav_entries, discover_routes

    definitions = discover_routes(config.routes_path)

    for defn in definitions:
        app.route(
            defn.path,
            methods=list(defn.methods),
            name=defn.name,
        )(defn.handler)

    # Inject navigation entries into template globals.
    # Templates can access these as {{ dynamic_routes }} to build nav menus.
    if definitions:
        nav_entries = build_nav_entries(definitions)
        app._template_globals["dynamic_routes"] = nav_entries

    return definitions


def _setup_reactive_pipeline(
    site: Site,
    app: App,
    config: PurrConfig,
    router: ContentRouter,
) -> tuple[Broadcaster, object, object]:
    """Set up the reactive pipeline for dev mode.

    Creates the broadcaster, dependency graph, mapper, pipeline coordinator,
    registers the SSE endpoint, and adds the HMR middleware.

    Returns the Broadcaster, ReactivePipeline, and StackCollector instances.

    """
    from purr.observability import EventLog, StackCollector
    from purr.reactive.broadcaster import Broadcaster
    from purr.reactive.graph import DependencyGraph
    from purr.reactive.hmr import hmr_middleware
    from purr.reactive.mapper import ReactiveMapper
    from purr.reactive.pipeline import ReactivePipeline

    broadcaster = Broadcaster()

    # Build the dependency graph.  In dev mode, the EffectTracer may not
    # be populated yet (it's built during a full build).  We create a
    # lightweight tracer for reactive use.
    try:
        from bengal.effects import EffectTracer

        tracer = EffectTracer()
    except Exception:
        tracer = None  # type: ignore[assignment]

    # Get the Kida environment from the Chirp app (if available)
    kida_env = getattr(app, "_kida_env", None) or getattr(app, "kida_env", None)

    # Create the unified observability collector
    event_log = EventLog()
    collector = StackCollector(event_log)

    graph = DependencyGraph(tracer=tracer, kida_env=kida_env)
    mapper = ReactiveMapper()
    pipeline = ReactivePipeline(
        graph=graph,
        mapper=mapper,
        broadcaster=broadcaster,
        site=site,
        collector=collector,
    )

    # Pre-parse content to populate AST cache
    pipeline.seed_ast_cache()

    # Register the SSE endpoint and stats endpoint
    router.register_sse_endpoint(broadcaster)
    router.register_stats_endpoint(collector)

    # Add error overlay middleware (catches render errors → styled HTML)
    from purr.reactive.error_overlay import error_overlay_middleware

    app.add_middleware(error_overlay_middleware)

    # Add HMR script injection middleware
    app.add_middleware(hmr_middleware)

    return broadcaster, pipeline, collector


def _start_watcher(config: PurrConfig, pipeline: object) -> object:
    """Start the ContentWatcher in a background thread.

    Returns the ContentWatcher instance (for shutdown coordination).

    """
    from purr.content.watcher import ContentWatcher

    watcher = ContentWatcher(config)
    watcher.start()
    return watcher


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def dev(root: str | Path = ".", **kwargs: object) -> None:
    """Start a content-reactive development server.

    Launches a Pounce server with single-worker mode and the full reactive
    pipeline active: file watcher, AST differ, reactive mapper, and SSE
    broadcaster.  Dynamic routes from ``routes/`` are discovered and registered.

    Args:
        root: Path to the site root directory.
        **kwargs: Override PurrConfig fields.

    """
    from purr import _set_site
    from purr.banner import print_banner

    config = PurrConfig(root=Path(root), **kwargs)
    t0 = time.perf_counter()

    # Load Bengal site and make it available via purr.site
    site = _load_site(config.root)
    _set_site(site)

    # Create Chirp app with debug enabled
    app = _create_chirp_app(config, debug=True)

    # Wire content routes
    router, page_count = _wire_content_routes(site, app)

    # Wire dynamic routes from routes/ directory
    dynamic_defs = _wire_dynamic_routes(app, config)

    # Set up reactive pipeline (SSE endpoint, HMR middleware, watcher)
    _broadcaster, pipeline, collector = _setup_reactive_pipeline(site, app, config, router)

    # Mount static files
    _mount_static_files(app, config)

    # Start file watcher in background
    watcher = _start_watcher(config, pipeline)

    load_ms = (time.perf_counter() - t0) * 1000

    # Banner
    print_banner(
        config, page_count, mode="dev",
        route_count=len(dynamic_defs), reactive=True,
        load_ms=load_ms,
    )

    # Run via Pounce (single worker, dev mode)
    # Pass the StackCollector as Pounce's lifecycle_collector so
    # connection events flow into the same EventLog as pipeline events.
    try:
        app.run(host=config.host, port=config.port, lifecycle_collector=collector)
    finally:
        # Clean shutdown
        if hasattr(watcher, "stop"):
            watcher.stop()


def build(root: str | Path = ".", **kwargs: object) -> None:
    """Export the site as static HTML files.

    Renders all routes (content pages + dynamic Chirp routes) to plain HTML
    files, copies static assets, and optionally generates a sitemap.  Output
    is deployable to any static hosting (CDN, GitHub Pages, S3, etc.).

    Args:
        root: Path to the site root directory.
        **kwargs: Override PurrConfig fields.

    """
    from purr.banner import print_banner
    from purr.export.static import StaticExporter

    config = PurrConfig(root=Path(root), **kwargs)
    t0 = time.perf_counter()

    # Load Bengal site
    site = _load_site(config.root)

    # Create Chirp app for template rendering
    app = _create_chirp_app(config)

    # Wire content routes (needed for template resolution)
    _router, page_count = _wire_content_routes(site, app)

    # Discover dynamic routes
    dynamic_defs = _wire_dynamic_routes(app, config)

    load_ms = (time.perf_counter() - t0) * 1000

    # Banner
    print_banner(
        config, page_count, mode="build",
        route_count=len(dynamic_defs),
        load_ms=load_ms,
    )

    # Run static export
    exporter = StaticExporter(
        site=site,
        app=app,
        config=config,
        routes=dynamic_defs,
    )
    result = exporter.export()

    # Print summary
    _print_export_summary(result)


def _print_export_summary(result: object) -> None:
    """Print export completion summary to stderr."""
    from purr.export.static import ExportResult

    if not isinstance(result, ExportResult):
        return

    lines = [
        "",
        "─" * 41,
        f"  Exported {result.total_pages} page{'s' if result.total_pages != 1 else ''}",
    ]
    if result.total_assets > 0:
        lines.append(
            f"  Copied {result.total_assets} asset{'s' if result.total_assets != 1 else ''}"
        )
    lines.append(f"  Output: {result.output_dir}")
    lines.append(f"  Done in {result.duration_ms:.0f}ms")

    print("\n".join(lines), file=sys.stderr)


def serve(root: str | Path = ".", **kwargs: object) -> None:
    """Run the site as a live Pounce server in production.

    Static content is served via Chirp routes.  Dynamic routes from
    ``routes/`` are discovered and handled per-request.  Multiple Pounce
    workers share the frozen Chirp app and immutable Bengal site data —
    no shared mutable state.

    Args:
        root: Path to the site root directory.
        **kwargs: Override PurrConfig fields.

    """
    from purr import _set_site
    from purr.banner import print_banner

    config = PurrConfig(root=Path(root), **kwargs)
    t0 = time.perf_counter()

    # Load Bengal site and make it available via purr.site
    site = _load_site(config.root)
    _set_site(site)

    # Create Chirp app (production mode — no debug, no reload)
    app = _create_chirp_app(config, debug=False)

    # Wire content routes
    _router, page_count = _wire_content_routes(site, app)

    # Wire dynamic routes from routes/ directory
    dynamic_defs = _wire_dynamic_routes(app, config)

    # Mount static files
    _mount_static_files(app, config)

    load_ms = (time.perf_counter() - t0) * 1000

    # Banner
    print_banner(
        config, page_count, mode="serve",
        route_count=len(dynamic_defs),
        load_ms=load_ms,
    )

    # Create observability collector for production mode
    from purr.observability import EventLog, StackCollector

    event_log = EventLog()
    collector = StackCollector(event_log)

    # Run via Pounce directly with multi-worker support
    from pounce.config import ServerConfig
    from pounce.server import Server

    server_config = ServerConfig(
        host=config.host,
        port=config.port,
        workers=config.workers,  # 0 = auto-detect via Pounce
    )
    server = Server(server_config, app, lifecycle_collector=collector)
    server.run()
