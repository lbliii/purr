# Product Requirements Document: Purr

**Version**: 0.1.0-dev
**Date**: 2026-02-07
**Status**: Phase 0 — scaffolding and vision

---

## 1. Overview

Purr is a content-reactive runtime that unifies the Bengal ecosystem into a single
developer experience. It connects Bengal (static site generation), Chirp (web framework),
and Pounce (ASGI server) through a reactive pipeline that propagates content changes
from edited Markdown files to browser DOM updates in milliseconds.

Purr is the integration layer — thin by design. The hard problems (parsing, templating,
routing, serving) are solved by the ecosystem libraries. Purr wires them together into
something that behaves like a new kind of tool: a content platform where the boundary
between static site and web application doesn't exist.

---

## 2. Problem Statement

### 2.1 The Gap

Every content tool forces a hard choice between static and dynamic:

| Approach | Tools | Limitation |
|----------|-------|-----------|
| Static site generator | Hugo, MkDocs, Sphinx, Astro | No dynamic features — need separate app |
| Web framework | Django, FastAPI, Flask | Overkill for content — no Markdown pipeline |
| Docs-as-a-service | Mintlify, Fern, GitBook | Vendor lock-in — can't extend or self-host |

When a documentation site needs search, authentication, or a dashboard, the team rewrites
in a web framework. When a web application needs a content section, the team bolts on a
CMS. Neither transition is smooth because static and dynamic tools don't share content
models, templates, or deployment infrastructure.

### 2.2 Why Now

The Bengal ecosystem has solved each layer independently:

1. **Patitas** produces a typed, frozen AST from Markdown — content is a data structure,
   not a string
2. **Kida** compiles templates to Python AST with block-level dependency analysis — the
   template engine knows which blocks depend on which variables
3. **Bengal** tracks file-level dependencies via EffectTracer — the build system knows
   which pages are affected by which files
4. **Chirp** supports SSE fragment streaming — the framework can push HTML fragments to
   the browser
5. **Pounce** serves with free-threading parallelism — the server handles concurrent SSE
   connections natively

These capabilities were designed independently but share the same architectural DNA
(frozen data, typed contracts, free-threading safety). Purr is the integration that
connects them into a reactive pipeline.

### 2.3 Specific Gaps Purr Fills

1. **No content-to-browser reactive pipeline.** Bengal detects file changes and knows which
   pages are affected. Chirp can push SSE fragments. But nothing connects them — no AST
   diffing, no block-level change mapping, no targeted fragment delivery.

2. **No unified content + routes.** Bengal serves static content. Chirp serves dynamic
   routes. There's no way to combine them in a single URL space with shared templates
   and navigation.

3. **No progressive deployment model.** There's no tool that lets you start with
   `purr build` (static export) and graduate to `purr serve` (live server) without
   rewriting content, templates, or routes.

---

## 3. Target Users

### 3.1 Primary: Python Developers Building Content Sites

Developers who need documentation, blogs, or content-heavy sites and want to stay in
the Python ecosystem. Today they use MkDocs (limited) or Sphinx (painful) for content,
and switch to FastAPI/Django when they need dynamic features.

**Needs:**
- Markdown-based content pipeline with modern features (directives, syntax highlighting)
- Clean, fast development loop (edit → see changes instantly)
- Ability to add dynamic routes (search, API endpoints) without leaving the stack
- Static export for simple deployments, live server for dynamic features
- Python 3.14+ (these are early adopters of modern Python)

### 3.2 Secondary: Teams Outgrowing Static Site Generators

Teams whose documentation or content site has grown to need dynamic features — search,
authentication, dashboards, real-time updates — and are facing a rewrite to a web
framework.

**Needs:**
- Migration path from pure static to static + dynamic without full rewrite
- Shared templates and navigation across static and dynamic pages
- Production deployment that handles both static content and dynamic routes

### 3.3 Tertiary: Bengal Ecosystem Contributors

Developers already using individual ecosystem libraries (Kida, Patitas, Rosettes) who
want to see them work together as a unified platform.

**Needs:**
- Reference integration showing the ecosystem's full potential
- Clear architecture for how the libraries compose
- Contribution paths (themes, plugins, routes)

---

## 4. Requirements

### 4.1 Three Modes

| Mode | Command | Description |
|------|---------|-------------|
| Dev | `purr dev` | Reactive local development with SSE updates |
| Build | `purr build` | Static export to HTML files |
| Serve | `purr serve` | Live production server with dynamic routes |

All three modes use the same content, templates, and configuration. The mode determines
deployment: files (build), local server (dev), or production server (serve).

### 4.2 Content Routing

- Bengal pages are served as Chirp routes (content router)
- User-defined Chirp routes coexist in the same URL space
- Shared template context: dynamic routes access the Bengal site model
- Navigation includes both static and dynamic pages

### 4.3 Reactive Pipeline (Dev Mode)

- File changes detected via filesystem watcher
- Changed Markdown re-parsed through Patitas (single file, not full site)
- AST diff identifies specific changed nodes
- Reactive mapper traces changes to affected template blocks
- Affected blocks re-rendered via Kida
- HTML fragments pushed to browser via SSE (Chirp)
- Target latency: < 100ms from file save to browser update

### 4.4 Static Export

- All content pages rendered to HTML (Bengal pipeline)
- Dynamic routes pre-rendered with default state
- Static assets copied with optional fingerprinting
- Output deployable to any static hosting (CDN, GitHub Pages, S3)

### 4.5 Production Serving

- Content pages served from memory (pre-rendered at startup)
- Dynamic routes handled per-request by Chirp
- SSE broadcasting active for connected clients
- Served by Pounce with free-threading parallelism
- Immutable site data shared across worker threads

---

## 5. Architecture Constraints

### 5.1 Purr is Thin

Purr adds no new parsing, templating, routing, or serving capabilities. It exclusively
integrates existing ecosystem libraries. New code is limited to:

- AST diffing (content/differ.py)
- Content-to-block mapping (reactive/mapper.py)
- SSE broadcast coordination (reactive/broadcaster.py)
- Content routing bridge (content/router.py)
- Static export orchestration (export/static.py)
- CLI and configuration (app.py, _cli.py, config.py)

### 5.2 No New Dependencies

Purr's runtime dependencies are exactly: bengal, chirp, and pounce. These transitively
bring in kida, patitas, rosettes, and their dependencies. Purr adds nothing else.

### 5.3 Free-Threading Safe

All Purr code follows the ecosystem's free-threading patterns:

- Frozen dataclasses for configuration and state
- ContextVar for request-scoped data
- threading.Lock only where shared mutable state is unavoidable
- `_Py_mod_gil = 0` declared

---

## 6. Success Metrics

### 6.1 Technical

- Reactive pipeline latency < 100ms (file save → browser update)
- Zero additional runtime dependencies beyond the ecosystem
- All tests passing with free-threading enabled
- `purr build` output byte-identical to Bengal's direct build (for content-only sites)

### 6.2 Developer Experience

- `purr dev` starts in < 2 seconds for a 50-page site
- Adding a dynamic route requires one Python file and one config line
- Switching from `purr build` to `purr serve` requires zero content changes

---

## 7. Out of Scope

- **Database integration.** Purr is a content runtime, not an ORM.
- **JavaScript build pipeline.** No bundling, transpiling, or Node.js.
- **Hosting platform.** Managed hosting is a separate product concern.
- **Visual editor.** Content manipulation UI is a future product opportunity.
- **Authentication/authorization.** Handled by Chirp middleware if needed.
- **Python < 3.14 support.** Ecosystem-wide requirement.

---

## 8. Dependencies on Ecosystem

Purr depends on specific capabilities in the ecosystem libraries:

| Capability | Library | Status |
|-----------|---------|--------|
| Typed, frozen Markdown AST | Patitas | Available (frozen dataclasses, hashable) |
| Block-level template dependency analysis | Kida | Available (block_metadata, depends_on) |
| File-level dependency tracking | Bengal | Available (EffectTracer, BuildCache) |
| SSE fragment streaming | Chirp | Available (EventStream, Fragment) |
| Free-threading ASGI server | Pounce | Available (thread-based workers) |
| AST diffing | Patitas | **Not yet built** (nodes are diffable by design) |
| Content-to-context mapping | Bengal/Purr | **Not yet built** (new in Purr) |
