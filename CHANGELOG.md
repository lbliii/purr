# Changelog

All notable changes to purr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Reactive pipeline: live updates not reaching the browser**
  - `PurrConfig` now resolves relative `root` paths to absolute in `__post_init__`, fixing a
    silent failure where `watchfiles` (absolute paths) could not be matched against a relative
    `config.root` via `Path.relative_to()`, causing all change events to be dropped.
  - `DependencyGraph` now lazily resolves the Kida environment from the Chirp app via a
    `kida_env` property, fixing `None` environment during pipeline setup (before app freeze).
    Empty results are no longer cached when the env is unavailable.
  - `CONTENT_CONTEXT_MAP` in the reactive mapper updated to use actual template context
    variable names (`content`, `toc`, `page`) matching what Kida's `DependencyWalker` detects,
    replacing incorrect paths (`page.body`, `page.toc`).
  - Default `page.html` template content block now includes `id="purr-content"` for HMR
    surgical DOM swaps.
  - Pipeline falls back to `purr:refresh` (full page reload) when the fragment update path
    produces zero block updates.

- **SSE `StopAsyncIteration` and `RuntimeError` noise in terminal**
  - Broadcaster's `client_generator` now catches `GeneratorExit` alongside
    `asyncio.CancelledError` to suppress `StopAsyncIteration` during cleanup.
  - Chirp's `produce_events` replaced `asyncio.wait_for(asyncio.shield(...))` with
    `asyncio.wait()` to avoid shield-callback noise, and wraps `send()` calls in
    `try/except RuntimeError` to handle client disconnections gracefully.
  - `ReactivePipeline._update_page_html` re-renders markdown to HTML and updates the Bengal
    `Page` object on every content change, ensuring manual refreshes always show current content.

### Added

- **Phase 5: Incremental Pipeline + Full-Stack Observability**

  #### Incremental AST Pipeline

  - Content changes now propagate in O(change) rather than O(document):
    - Patitas `parse_incremental` re-parses only the affected blocks, reusing unchanged AST
      nodes with adjusted offsets
    - Kida `detect_block_changes` + `recompile_blocks` selectively recompile only the
      template blocks that changed, patching the live Template object
    - `_compute_edit_region` in the reactive pipeline identifies the minimal differing
      byte range between old and new source text
  - `ReactivePipeline._handle_content_change` orchestrates the full incremental path:
    incremental parse → diff → selective block recompile → SSE broadcast
  - Content cache stores both AST and source text (`_CachedContent`) to enable edit region
    computation for subsequent changes
  - Falls back to full re-parse and full recompile transparently on failure

  #### Full-Stack Observability

  - `purr.observability` — unified event model across the vertical stack:
    - `ContentParsed` — records full vs incremental parse, blocks reused/reparsed, timing
    - `ContentDiffed` — records AST diff results (added, removed, modified counts)
    - `BuildEvent` — records build actions (render, copy_asset, write_index, etc.)
    - `ReactiveEvent` — records SSE broadcasts (blocks updated, clients notified, timing)
    - `BlockRecompiled` — records individual block recompilations with reason
    - `StackEvent` — union type of all the above
  - `EventLog` — thread-safe bounded ring buffer with query support (by event type, time
    range, file path). Configurable capacity (default 10,000 events).
  - `StackCollector` — unified collector that implements Pounce's `LifecycleCollector`
    protocol. Receives connection events from Pounce workers and pipeline events from
    Purr's reactive system, all flowing into a single `EventLog`.
  - `ReactivePipeline` instrumented at every stage: parse, diff, block recompile, and
    broadcast events are recorded automatically when a collector is present.
  - `_setup_reactive_pipeline` creates the `EventLog` + `StackCollector` automatically in
    dev mode. `dev()` passes the collector through Chirp to Pounce. `serve()` creates its
    own collector and passes it directly to Pounce's Server.
  - 18 new observability tests covering EventLog, StackCollector, thread safety, and event
    immutability, bringing total to 282.

- **Phase 4: Static Export** — pre-render all routes to static HTML files
  - `export/static.py` — `StaticExporter` orchestrates the full export pipeline: content
    page rendering, dynamic route pre-rendering, asset copying, error pages, and sitemap
    generation. `ExportedFile` and `ExportResult` frozen dataclasses track export metadata.
  - `export/assets.py` — recursive asset copying with hidden file skipping, opt-in
    content-hash fingerprinting (`style.a1b2c3d4.css`), HTML reference rewriting, and
    `manifest.json` generation mapping original to fingerprinted paths.
  - `export/sitemap.py` — `sitemap.xml` generation from exported pages. Content and dynamic
    pages included, assets excluded. Requires `base_url` in config.
  - Dynamic route pre-rendering via Chirp's `TestClient` — GET routes only, with
    `exportable = False` module-level opt-out for routes that shouldn't be pre-rendered.
  - 404 error page rendering: exports `404.html` if the template exists.
  - Clean URL convention: `/docs/intro/` writes to `output/docs/intro/index.html`.
  - Output directory cleaned before each export.
  - `base_url` and `fingerprint` fields added to `PurrConfig`.
  - `--base-url` and `--fingerprint` CLI flags on `purr build`.
  - `build()` in `app.py` rewritten to use `StaticExporter` (replaces direct Bengal
    `BuildOrchestrator` delegation). Export summary printed to stderr.
  - 75 new tests (20 exporter + 15 assets + 11 sitemap + 9 CLI + 11 integration + 9 config)
    bringing total to 254.

- **Phase 3: Dynamic Routes** — user-defined Chirp routes alongside Bengal content
  - `routes/loader.py` — file-path convention route discovery. `routes/search.py` becomes
    `GET /search`. Function names (`get`, `post`, `put`, `delete`, `patch`) map to HTTP
    methods. Optional `path`, `name`, `nav_title` module-level overrides.
  - `routes/__init__.py` — public API: `discover_routes()`, `build_nav_entries()`
  - `purr.site` accessor — module-level reference to the Bengal Site, available to dynamic
    route handlers via `from purr import site`. Set once at startup, immutable thereafter.
  - `_wire_dynamic_routes()` in `app.py` — discovers routes, registers on Chirp app, injects
    `NavEntry` objects into template globals as `dynamic_routes`
  - `dev()` and `serve()` now discover and register dynamic routes from `routes/` directory
  - Startup banner shows dynamic route count alongside page count
  - Route file changes in dev mode trigger restart-required message (route table is frozen)
  - `RoutePath` and `HandlerFunc` type aliases in `_types.py`
  - `[tool.uv.sources]` added to `pyproject.toml` for local ecosystem deps (bengal, chirp,
    pounce). `uv.lock` generated for reproducible builds.
  - 47 new tests (34 route loader + 5 site context + 8 integration) bringing total to 179

- **Phase 2: Reactive Pipeline** — content changes propagate to the browser via SSE
  - `content/differ.py` — structural tree diff on Patitas frozen ASTs with fast-path
    subtree skipping via `==` on frozen nodes. Produces `ASTChange` tuples.
  - `content/watcher.py` — file watcher using `watchfiles` with change categorization
    (content, template, config, asset, route). Bridges to asyncio via queue.
  - `reactive/graph.py` — unified dependency graph combining Bengal's `EffectTracer`
    (file-level) with Kida's `block_metadata()` (block-level). Cached per template.
  - `reactive/mapper.py` — maps AST node changes to affected template blocks using
    `CONTENT_CONTEXT_MAP` and Kida's block dependency analysis. Conservative fallback
    for unknown node types.
  - `reactive/broadcaster.py` — per-page SSE subscriber management with `Fragment`
    and `SSEEvent` push. Thread-safe subscriber map.
  - `reactive/pipeline.py` — coordinator connecting watcher to broadcaster with AST
    cache, content/template/config change routing, and Patitas re-parse.
  - `reactive/hmr.py` — HMR middleware injecting native `EventSource` script into
    HTML responses for live DOM updates in dev mode.
  - `/__purr/events` SSE endpoint registered via `ContentRouter.register_sse_endpoint()`
  - `dev()` now wires the full reactive pipeline: dependency graph, mapper, broadcaster,
    watcher, SSE endpoint, and HMR middleware.
  - `watchfiles>=1.0.0` added as a core dependency
  - 108 new tests (96 unit + 12 integration) bringing total to 132

- **Phase 1: Content Router** — Bengal pages served as Chirp routes
  - `ContentRouter` discovers Bengal pages and registers each as a Chirp GET route
  - Template resolution: frontmatter override, index detection, `page.html` default
  - Full Bengal template context via `build_page_context()` passed to Kida
- `dev()` — loads Bengal site, creates Chirp app, wires routes, runs Pounce (single worker)
- `build()` — loads Bengal site, delegates to Bengal's `BuildOrchestrator`
- `serve()` — loads Bengal site, runs Pounce with configurable multi-worker support
- Static file serving via Chirp's `StaticFiles` middleware
- Startup banner with page count, template path, and mode-specific info
- `PurrMode` narrowed to `Literal["dev", "build", "serve"]`
- 24 new tests (9 unit, 12 integration, 3 end-to-end via Chirp test client)

### Phase 0

- Project scaffolding: `pyproject.toml`, `src/` layout, ruff/ty/pytest configuration
- Vision and roadmap documentation
- Module stubs for content, reactive, and export subsystems
