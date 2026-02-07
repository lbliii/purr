# Purr

**A content-reactive runtime for Python 3.14t.**

Purr is the integration layer that unifies the Bengal ecosystem into a single content-reactive
runtime. Edit content, see the browser update surgically. Add dynamic routes alongside static
pages without changing tools. Deploy as static files or run as a live server. The boundary
between static site and web application disappears.

Named after the sound of a Bengal cat at rest, purr is part of a family of Python tools:
**bengal** (static site generator), **chirp** (web framework), **kida** (template engine),
**patitas** (markdown parser), **rosettes** (syntax highlighter), and **pounce** (ASGI server).

---

## Why Purr Exists

Every existing content tool forces a choice: static site or web application.

**Static site generators** (Hugo, MkDocs, Sphinx, Astro) build HTML files from content.
They're fast, simple, and deployable anywhere. But when you need search, authentication,
a dashboard, or a real-time feed — you leave the static world entirely and rebuild in a
framework. Your content model, templates, and toolchain don't transfer.

**Web frameworks** (Django, FastAPI, Flask, Next.js) handle dynamic content natively. But
they're overkill for a documentation site, and their content story is a database or an
afterthought. You don't get a Markdown pipeline, template analysis, or incremental builds.

**Docs-as-a-service platforms** (Mintlify, Fern, GitBook) abstract away the infrastructure.
But you're renting their rendering pipeline. When you outgrow their capabilities, you
rewrite.

The Bengal ecosystem already solves each piece:

| Project | Capability |
|---------|-----------|
| **Patitas** | Typed Markdown AST (frozen, hashable, diffable nodes) |
| **Rosettes** | Syntax highlighting (55 languages, O(n) state machines) |
| **Kida** | Template compilation to Python AST with block-level dependency analysis |
| **Bengal** | Static site generation with file-level dependency tracking (EffectTracer) |
| **Chirp** | Web framework with SSE fragment streaming and htmx integration |
| **Pounce** | ASGI server with free-threading-native worker model |

What's missing is the **integration** — the layer that connects Bengal's dependency graph to
Chirp's SSE pipeline, that maps Patitas AST changes to Kida template blocks, that makes
"static site that becomes a dynamic app" a single command instead of a rewrite.

Purr is that layer.

---

## The Core Insight

**Content is a reactive data structure, not a build artifact.**

Every existing stack treats content as either static files that get built into HTML, or
database rows that get queried on each request. Purr treats content as a typed, observable
graph where changes propagate through a pipeline:

```
Edit Markdown file
    → Patitas re-parses the changed file (typed AST)
    → AST differ identifies which nodes changed
    → Reactive mapper traces changes through Bengal's dependency graph
    → Kida re-renders only the affected template blocks
    → Chirp pushes updated HTML fragments via SSE
    → Browser swaps the DOM (htmx, no JS framework)
```

Every step is typed, traceable, and parallelizable. The entire pipeline runs in milliseconds
because each component was designed for this — frozen ASTs, block-level dependency analysis,
streaming template rendering, surgical fragment updates.

This isn't hot-reload. Hot-reload rebuilds the page. This traces a content change through
the dependency graph to the exact DOM element that needs updating.

---

## Design Principles

These follow directly from the Bengal ecosystem — the same instincts that shaped every
project in the family.

### 1. The obvious thing should be the easy thing

`purr dev` starts a content-reactive development server. `purr build` exports static files.
`purr serve` runs in production. You don't need to understand the reactive pipeline to use
it — it just works. The architecture reveals itself when you need it.

### 2. Data should be honest about what it is

Static content is rendered once and served from memory. Dynamic routes are computed per
request. The system is transparent about which pages are static and which are dynamic — but
the user experience is seamless. No fake dynamism, no unnecessary computation.

### 3. Extension should be structural, not ceremonial

Adding a dynamic route is creating a Python function. No base classes, no registration
ceremony. If a function returns a Response, it's a route. If a directory has Markdown files,
they're content. The system discovers capability from shape.

### 4. The system should be transparent

A content change propagates through a typed pipeline: AST diff → dependency graph →
template blocks → SSE fragments. Every step is inspectable. `purr dev` logs exactly which
blocks were affected and why.

### 5. Own what matters, delegate what doesn't

Purr owns the integration — the reactive pipeline, the content router, the mode selection.
It delegates everything else to the libraries that already solve those problems: Bengal for
content, Chirp for HTTP, Kida for templates, Patitas for parsing, Pounce for serving.

---

## Architecture

### Module Layout

```
purr/
├── __init__.py              # Public API: dev(), build(), serve(), PurrConfig
├── py.typed                 # PEP 561
│
│   # Primitives
├── _types.py                # Shared type definitions
├── _errors.py               # PurrError hierarchy
├── config.py                # PurrConfig — frozen dataclass
│
│   # Content Layer — Bengal pages as reactive data
├── content/
│   ├── __init__.py
│   ├── router.py            # Bengal pages → Chirp routes
│   ├── watcher.py           # File change → reactive pipeline trigger
│   └── differ.py            # Patitas AST diffing (structural tree diff)
│
│   # Reactive Layer — Change propagation
├── reactive/
│   ├── __init__.py
│   ├── graph.py             # Unified dependency graph (content + templates)
│   ├── mapper.py            # AST change → template block mapping
│   └── broadcaster.py       # SSE broadcast to connected clients
│
│   # Export Layer — Static output
├── export/
│   ├── __init__.py
│   └── static.py            # Pre-render live app → static files
│
│   # Application
├── app.py                   # PurrApp — unified Bengal + Chirp application
└── _cli.py                  # CLI: purr dev / purr build / purr serve
```

### Core Abstractions

```
┌───────────────────────────────────────────────────────────────┐
│  Interface Layer — What users touch                           │
│                                                               │
│  purr dev          purr build          purr serve             │
│  PurrConfig        purr.yaml                                  │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│  Application Layer — Unified content + routes                 │
│                                                               │
│  PurrApp (wraps Bengal Site + Chirp App)                      │
│  ContentRouter (Bengal pages → Chirp routes)                  │
│  User routes (routes/*.py → Chirp handlers)                   │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│  Reactive Layer — Change propagation pipeline                 │
│                                                               │
│  FileWatcher → ASTDiffer → DependencyGraph → BlockMapper      │
│                                          → SSEBroadcaster     │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│  Ecosystem Layer — Bengal + Chirp + Pounce                    │
│                                                               │
│  Bengal (content pipeline, EffectTracer, incremental builds)  │
│  Chirp (routing, SSE, Fragment rendering, middleware)         │
│  Pounce (ASGI server, free-threading workers)                 │
│  Kida (template compilation, dependency analysis)             │
│  Patitas (Markdown parsing, typed AST)                        │
│  Rosettes (syntax highlighting)                               │
└───────────────────────────────────────────────────────────────┘
```

### The Reactive Pipeline

```
                    ┌─────────────┐
                    │  File Edit  │
                    │  (watchfiles)│
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Re-parse   │  Patitas: parse single file → AST
                    │  (Patitas)  │  ~5-10ms for a typical page
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  AST Diff   │  Compare old/new frozen ASTs
                    │  (differ)   │  Fast-path: skip unchanged subtrees
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Map to     │  Kida block_metadata() + Bengal EffectTracer
                    │  Blocks     │  "Heading changed → page.toc → sidebar block"
                    │  (mapper)   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Re-render  │  Kida render_block() for affected blocks only
                    │  Blocks     │  ~2-5ms per block
                    │  (Kida)     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Push SSE   │  Chirp Fragment via EventStream
                    │  (Chirp)    │  Targeted to subscribers of this page
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  DOM Swap   │  htmx swaps the affected element
                    │  (browser)  │  No full reload, no flash
                    └─────────────┘
```

---

## Three Modes

### `purr dev` — Local Development

The primary developer experience. Starts a Pounce server locally with the full reactive
pipeline active.

```bash
purr dev

 Purr v0.1.0 — content-reactive runtime
 ─────────────────────────────────────────
 ✓ Loaded 12 pages, 3 sections
 ✓ Compiled 5 templates (Kida)
 ✓ Built dependency graph (47 edges)
 ✓ Live mode active — SSE broadcasting on /__purr/events

 → http://localhost:3000

 Watching for changes...
```

Edit a Markdown file, see the browser update in milliseconds. Template changes trigger
targeted fragment updates or full page refreshes depending on scope. Config changes
propagate through the dependency graph.

### `purr build` — Static Export

Renders everything to static HTML. The output is plain files deployable to any CDN.

```bash
purr build --output dist/
```

This is Bengal's build pipeline, extended to also pre-render any dynamic Chirp routes with
their default state. The output works without a server.

### `purr serve` — Live Production

Runs the full reactive stack on Pounce in production.

```bash
purr serve --host 0.0.0.0 --port 8000 --workers 4
```

Static content is served from memory (pre-rendered at startup). Dynamic routes are handled
by Chirp. SSE broadcasting is active for connected clients. This is for sites that need
dynamic features: search, APIs, dashboards, real-time content updates.

---

## The Static-to-Dynamic Continuum

A Purr project starts as a content site:

```
my-site/
├── content/
│   ├── _index.md
│   └── docs/
│       └── getting-started.md
├── templates/
│   └── page.html
└── purr.yaml
```

When you need a dynamic route, add it:

```python
# routes/search.py

from chirp import Request, Response
from purr import site

async def search(request: Request) -> Response:
    query = request.query.get("q", "")
    results = site.search(query)
    return Response.template("search.html", query=query, results=results)
```

```yaml
# purr.yaml
routes:
  - path: /search
    handler: routes.search:search
```

The search page uses the same Kida templates, appears in the same navigation, and runs
alongside static content. From the browser, it's just another page.

Deploy with `purr build` for static-only. Deploy with `purr serve` when you have dynamic
routes. No rewrite required.

---

## Phased Roadmap

### Phase 0: Foundation ✓

Project scaffolding, vision, architecture documentation.

- [x] Repository structure matching Bengal ecosystem conventions
- [x] `pyproject.toml` with ruff/ty/pytest/poe configuration
- [x] Vision document (ROADMAP.md)
- [x] Module stubs for content, reactive, and export subsystems

### Phase 1: Content Router

Serve Bengal pages as Chirp routes. The minimal viable integration — `purr dev` starts a
server that renders Bengal content through Chirp.

**Content layer:**

- [ ] `config.py` — `PurrConfig` frozen dataclass (site root, mode, host, port)
- [ ] `content/router.py` — discover Bengal pages, register as Chirp routes
- [ ] `app.py` — `PurrApp` wrapping Bengal `Site` + Chirp `App`
- [ ] `_cli.py` — `purr dev` and `purr build` commands

**Integration:**

- [ ] Load Bengal site content at startup
- [ ] Render pages through Kida templates via Chirp's template integration
- [ ] Serve static assets alongside rendered content
- [ ] `purr build` delegates to Bengal's existing build pipeline

**Tests:**

- [ ] Unit tests for content routing
- [ ] Integration test: content site served through Purr
- [ ] Integration test: `purr build` produces static output

### Phase 2: Reactive Pipeline

The core innovation — content changes propagate to the browser via SSE.

**AST diffing:**

- [ ] `content/differ.py` — structural tree diff on Patitas frozen ASTs
- [ ] Fast-path: `==` comparison on subtrees (skip unchanged)
- [ ] `ASTChange` dataclass: kind, path, old_node, new_node, location

**Reactive mapping:**

- [ ] `reactive/graph.py` — unified dependency graph combining Bengal's EffectTracer
  with Kida's block-level dependency analysis
- [ ] `reactive/mapper.py` — map AST changes to affected template blocks using
  Kida's `block_metadata()` and `depends_on()`
- [ ] Content-to-context mapping: "Heading changed → page.toc → sidebar block"

**File watching:**

- [ ] `content/watcher.py` — file change detection triggering the reactive pipeline
- [ ] Selective re-parse: only re-parse changed files through Patitas
- [ ] Integration with Bengal's `EffectTracer` for transitive dependencies

**SSE broadcasting:**

- [ ] `reactive/broadcaster.py` — manage SSE connections per page
- [ ] Push `Fragment` updates via Chirp's `EventStream`
- [ ] Minimal client-side JS/htmx snippet injected in dev mode
- [ ] Cascade handling: config changes → nav/header blocks across all pages
- [ ] Template changes → full page refresh for affected pages

**Tests:**

- [ ] Unit tests for AST differ (added, removed, modified nodes)
- [ ] Unit tests for reactive mapper (content change → block identification)
- [ ] Integration test: edit Markdown → browser receives SSE fragment
- [ ] Edge cases: cascade changes, template inheritance chains

### Phase 3: Dynamic Routes

Serve user-defined Chirp routes alongside Bengal content.

**Route integration:**

- [ ] Discover and load routes from `routes/` directory
- [ ] Merge dynamic routes with content routes in Chirp's router
- [ ] Shared template context: dynamic routes access `site` object
- [ ] Navigation integration: dynamic pages appear in site nav

**Production mode:**

- [ ] `purr serve` — run as live Pounce server in production
- [ ] Static content served from memory (pre-rendered at startup)
- [ ] Dynamic routes handled by Chirp per-request
- [ ] Worker-safe: immutable site data shared across Pounce threads

**Tests:**

- [ ] Unit tests for route discovery and loading
- [ ] Integration test: mixed static + dynamic routes
- [ ] Integration test: `purr serve` under Pounce with multiple workers

### Phase 4: Static Export

Pre-render the live app as static files, including dynamic routes.

**Export pipeline:**

- [ ] `export/static.py` — render all routes (static + dynamic) to files
- [ ] Dynamic route pre-rendering with default state
- [ ] Asset fingerprinting and manifest generation
- [ ] Sitemap generation

**Tests:**

- [ ] Unit tests for export pipeline
- [ ] Integration test: exported site matches live rendering

### Phase 5: Polish

Developer experience, performance, and ecosystem integration.

- [ ] Startup banner with clear status reporting
- [ ] Error overlay in dev mode (render errors as styled HTML in browser)
- [ ] Performance profiling: measure end-to-end reactive pipeline latency
- [ ] Default theme (production-quality, matches Bengal ecosystem aesthetic)
- [ ] `purr init` scaffolding command
- [ ] Documentation site (built with Purr, naturally)

---

## Non-Goals

Purr deliberately does not:

- **Duplicate functionality from the ecosystem.** Content parsing is Patitas. Templates are
  Kida. Routing is Chirp. Serving is Pounce. Building is Bengal. Purr integrates, it doesn't
  reimplement.
- **Include a database layer.** Purr is a content runtime, not an application framework. If
  you need a database, use it directly in your Chirp routes.
- **Include a JavaScript build pipeline.** No bundling, no transpiling. The stack is
  server-rendered HTML with htmx for interactivity. If you need a JS build step, use
  external tooling.
- **Support Python < 3.14.** Free-threading and the ecosystem's Python version requirement
  apply uniformly.
- **Compete with general-purpose frameworks.** Django, FastAPI, and Rails solve different
  problems. Purr is for content-first applications that need dynamic capabilities.
- **Be a hosting platform.** Purr is open source infrastructure. Managed hosting is a
  separate concern.

---

## Dependencies

### Core

```
purr (content-reactive runtime)
├── bengal    # Content pipeline, dependency tracking, incremental builds
├── chirp     # Web framework, SSE, fragments, middleware
└── pounce    # ASGI server, free-threading workers
    └── h11   # HTTP/1.1 parser
```

Bengal, Chirp, and Pounce bring their own dependencies (Kida, Patitas, Rosettes). Purr adds
no additional runtime dependencies beyond the ecosystem itself.

### Optional

```
pip install purr[full]    # Passes through to pounce[full] — H2, WebSocket, TLS
```

---

## The Stack

Purr completes the Bengal ecosystem — the layer that connects everything:

```
purr        Content runtime   (connects everything)
pounce      ASGI server       (serves apps)
chirp       Web framework     (serves HTML)
kida        Template engine   (renders HTML)
patitas     Markdown parser   (parses content)
rosettes    Syntax highlighter (highlights code)
bengal      Static site gen   (builds sites)
```

Each tool is independent. Together they form a complete content platform, built for
Python 3.14t, with minimal external dependencies at every layer.

---

*Purr: because when everything works together, you can hear it.*
