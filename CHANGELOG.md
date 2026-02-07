# Changelog

All notable changes to purr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
