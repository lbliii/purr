"""Purr application — the unified Bengal + Chirp integration.

PurrApp wraps a Bengal Site and a Chirp App into a single content-reactive application.
The three public functions (dev, build, serve) are the primary entry points.
"""

import importlib.util
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from purr._errors import ConfigError, ContentError
from purr.config import PurrConfig
from purr.config_loader import load_config

if TYPE_CHECKING:
    from bengal.core.site import Site
    from chirp import App

    from purr.content.router import ContentRouter
    from purr.reactive.broadcaster import Broadcaster
    from purr.routes.loader import RouteDefinition


def _parse_pages(site: Site) -> None:
    """Parse markdown content for all discovered pages.

    Bengal separates discovery from parsing.  Rather than pulling in the
    full ``RenderingPipeline`` / ``BuildOrchestrator`` machinery, we use
    Patitas' ``Markdown`` class directly with common extensions enabled
    (tables, strikethrough, task lists, footnotes).
    """
    from patitas import Markdown

    md = Markdown(plugins=["table"])

    for page in site.pages:
        raw = getattr(page, "_raw_content", "") or ""
        if not raw:
            continue
        page.html_content = md(raw)


def _load_site(root: Path) -> Site:
    """Load a Bengal site from the given root directory.

    Loads configuration via ``Site.from_config()`` and then discovers
    content (pages, sections, assets) via ``ContentOrchestrator``.

    Raises:
        ConfigError: If the site cannot be loaded (missing config, bad structure).

    """
    try:
        from bengal.core.site import Site

        site = Site.from_config(root)

        # Discover content — Site.from_config only loads configuration,
        # the ContentOrchestrator populates pages and sections.
        from bengal.orchestration.content import ContentOrchestrator

        orchestrator = ContentOrchestrator(site)
        orchestrator.discover()

        # Parse markdown to HTML — Bengal separates discovery from parsing.
        # We use Patitas directly for a lightweight parse pass rather than
        # pulling in the full RenderingPipeline + BuildOrchestrator.
        _parse_pages(site)

        return site
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
    #
    # Chirp's app.py binds ``create_environment`` via a ``from`` import,
    # so we must patch the name in ``chirp.app`` directly.  The patch is
    # guard-claused: it only activates when ``cfg.template_dir`` matches
    # the Purr app's primary template dir.  For any other App the
    # original function is called, preventing leakage in tests.
    import chirp.app as _chirp_app

    _orig_create_env = _chirp_app.create_environment
    _primary_dir = str(template_dirs[0])

    def _create_env_guarded(
        cfg: object, filters: dict, globals_: dict,
    ) -> object:
        # Only apply multi-path loading for the Purr-managed app.
        if str(getattr(cfg, "template_dir", None)) != _primary_dir:
            return _orig_create_env(cfg, filters, globals_)

        from kida import ChoiceLoader, Environment, FileSystemLoader, PackageLoader

        loaders: list[FileSystemLoader | PackageLoader] = [
            FileSystemLoader(template_dirs),
        ]
        # Chirp's built-in macros
        loaders.append(PackageLoader("chirp.templating", "macros"))
        # chirp-ui if installed
        try:
            import chirp_ui  # noqa: F401

            loaders.append(PackageLoader("chirp_ui", "templates"))
        except ImportError:
            pass

        env = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=cfg.autoescape,  # type: ignore[attr-defined]
            auto_reload=cfg.debug,  # type: ignore[attr-defined]
            trim_blocks=cfg.trim_blocks,  # type: ignore[attr-defined]
            lstrip_blocks=cfg.lstrip_blocks,  # type: ignore[attr-defined]
        )
        from chirp.templating.filters import BUILTIN_FILTERS

        env.update_filters(BUILTIN_FILTERS)
        if filters:
            env.update_filters(filters)
        for name, value in globals_.items():
            env.add_global(name, value)
        return env

    _chirp_app.create_environment = _create_env_guarded  # type: ignore[assignment]

    app = App(config=app_config)

    # chirp-ui integration when installed
    try:
        import chirp_ui as _chirp_ui
        from chirp.ext.chirp_ui import use_chirp_ui

        use_chirp_ui(app)
        _chirp_ui.register_filters(app)
    except ImportError:
        pass

    return app


def _resolve_load_user(config: PurrConfig) -> object | None:
    """Resolve load_user callable from config.auth_load_user.

    Format: ``module:attr`` (e.g. ``auth:load_user`` for routes/auth.py).
    Returns the callable or None if not configured.
    """
    spec = config.auth_load_user
    if not spec or ":" not in spec:
        return None
    module_part, _, attr = spec.partition(":")
    if not module_part or not attr:
        return None
    py_file = config.routes_path / f"{module_part}.py"
    if not py_file.is_file():
        msg = f"auth_load_user {spec!r}: {py_file} not found"
        raise ConfigError(msg)
    module_name = f"purr_auth_{module_part}"
    spec_obj = importlib.util.spec_from_file_location(module_name, py_file)
    if spec_obj is None or spec_obj.loader is None:
        msg = f"auth_load_user {spec!r}: failed to load {py_file}"
        raise ConfigError(msg)
    module = importlib.util.module_from_spec(spec_obj)
    sys.modules[module_name] = module
    spec_obj.loader.exec_module(module)  # type: ignore[union-attr]
    callable_obj = getattr(module, attr, None)
    if not callable(callable_obj):
        msg = f"auth_load_user {spec!r}: {attr} not callable in {py_file}"
        raise ConfigError(msg)
    return callable_obj


def _wire_auth_middleware(app: App, config: PurrConfig) -> None:
    """Add session, auth, and CSRF middleware when config.auth is True."""
    if not config.auth:
        return
    secret = config.session_secret or "dev-only-not-for-production"
    load_user = _resolve_load_user(config)
    if load_user is None:
        msg = "auth=True requires auth_load_user (e.g. auth:load_user)"
        raise ConfigError(msg)
    try:
        from chirp.middleware.auth import AuthConfig, AuthMiddleware
        from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware, csrf_field
        from chirp.middleware.sessions import SessionConfig, SessionMiddleware
    except ImportError as exc:
        msg = (
            "auth=True requires chirp[sessions,auth]. "
            "Install with: pip install chirp[sessions,auth]"
        )
        raise ConfigError(msg) from exc
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key=secret)))
    app.add_middleware(AuthMiddleware(AuthConfig(load_user=load_user)))
    app.add_middleware(CSRFMiddleware(CSRFConfig()))
    app.template_global("csrf_field")(csrf_field)


def _wire_template_globals(site: Site, app: App) -> None:
    """Inject site and nav_sections into template globals for all templates."""
    app._template_globals["site"] = site
    app._template_globals["nav_sections"] = [
        {"title": s.title or s.name, "href": getattr(s, "href", f"/{s.name}/")}
        for s in site.sections
        if getattr(s, "title", None) or getattr(s, "name", None)
    ]


def _wire_content_routes(
    site: Site, app: App, config: PurrConfig
) -> tuple[ContentRouter, int]:
    """Register Bengal content pages as Chirp routes.

    When config.auth is True, pages with gated metadata (config.gated_metadata_key)
    are wrapped with @login_required.

    Returns the ContentRouter instance and the number of pages registered.

    Raises:
        ContentError: If route registration fails.

    """
    from purr.content.router import ContentRouter

    try:
        router = ContentRouter(site, app, config)
        router.register_pages()
        return router, router.page_count
    except Exception as exc:
        msg = f"Failed to register content routes: {exc}"
        raise ContentError(msg) from exc


def _mount_static_files(app: App, config: PurrConfig) -> None:
    """Mount static file middleware with theme fallback.

    Mounts user static directory first, then bundled theme assets.
    chirp-ui (chirpui.css, themes/, chirpui-transitions.css) is served
    via use_chirp_ui() in _create_chirp_app when chirp-ui is installed.
    All served under ``/static``. User files take precedence.

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

    # Create the unified observability collector
    event_log = EventLog()
    collector = StackCollector(event_log)

    # DependencyGraph resolves kida_env lazily from the app reference
    # because the Kida environment isn't created until Chirp's _freeze().
    graph = DependencyGraph(tracer=tracer, app=app, site=site)
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


def _start_watcher(config: PurrConfig, pipeline: object, app: App) -> object:
    """Wire the ContentWatcher to the reactive pipeline via Chirp lifecycle hooks.

    Registers ``on_startup`` / ``on_shutdown`` hooks on *app* so that the
    async watcher task lives inside the event loop managed by Pounce.

    Flow:
        on_startup  → spawn ``_consume_events`` task (runs ``awatch`` internally)
        file change → async iteration → pipeline.handle_change()
        on_shutdown → cancel consumer task (cleanly tears down ``awatch``)

    Returns the ContentWatcher instance (for external reference, if needed).

    """
    import asyncio

    from purr.content.watcher import ContentWatcher
    from purr.reactive.pipeline import ReactivePipeline

    watcher = ContentWatcher(config)
    _task: asyncio.Task[None] | None = None

    @app.on_startup
    async def _start_event_consumer() -> None:
        nonlocal _task

        async def _consume_events() -> None:
            assert isinstance(pipeline, ReactivePipeline)
            async for event in watcher.changes():
                try:
                    await pipeline.handle_change(event)
                except Exception as exc:
                    print(f"  Pipeline error: {exc}", file=sys.stderr)

        _task = asyncio.create_task(_consume_events())

    @app.on_shutdown
    async def _stop_event_consumer() -> None:
        if _task is not None and not _task.done():
            _task.cancel()

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

    config = load_config(Path(root), **kwargs)
    t0 = time.perf_counter()

    # Load Bengal site and make it available via purr.site
    site = _load_site(config.root)
    _set_site(site)

    # Create Chirp app with debug enabled
    app = _create_chirp_app(config, debug=True)
    _wire_auth_middleware(app, config)

    # Wire content routes
    router, page_count = _wire_content_routes(site, app, config)

    # Inject site and nav_sections for all templates (including dynamic routes)
    _wire_template_globals(site, app)

    # Wire dynamic routes from routes/ directory
    dynamic_defs = _wire_dynamic_routes(app, config)

    # Set up reactive pipeline (SSE endpoint, HMR middleware, watcher)
    _broadcaster, pipeline, collector = _setup_reactive_pipeline(site, app, config, router)

    # Mount static files
    _mount_static_files(app, config)

    # Wire file watcher → reactive pipeline (starts on app startup)
    _start_watcher(config, pipeline, app)

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
    # Watcher shutdown is handled by the on_shutdown hook registered above.
    app.run(host=config.host, port=config.port, lifecycle_collector=collector)


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

    config = load_config(Path(root), **kwargs)
    t0 = time.perf_counter()

    # Load Bengal site
    site = _load_site(config.root)

    # Create Chirp app for template rendering
    app = _create_chirp_app(config)
    _wire_auth_middleware(app, config)

    # Wire content routes (needed for template resolution)
    _router, page_count = _wire_content_routes(site, app, config)

    # Inject site and nav_sections for all templates
    _wire_template_globals(site, app)

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

    config = load_config(Path(root), **kwargs)
    t0 = time.perf_counter()

    # Load Bengal site and make it available via purr.site
    site = _load_site(config.root)
    _set_site(site)

    # Create Chirp app (production mode — no debug, no reload)
    app = _create_chirp_app(config, debug=False)
    _wire_auth_middleware(app, config)

    # Wire content routes
    _router, page_count = _wire_content_routes(site, app, config)

    # Inject site and nav_sections for all templates
    _wire_template_globals(site, app)

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
