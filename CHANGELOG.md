# Changelog

All notable changes to purr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
