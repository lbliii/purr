# Product Requirements Document: Purr

**Version**: 0.1.0-dev
**Date**: 2026-02-07
**Status**: Phase 1 — content router complete

---

## 1. Overview

Purr is a content-reactive runtime that unifies the Bengal ecosystem into a single developer
experience. It connects Bengal (static site generation), Chirp (web framework), and Pounce
(ASGI server) through a reactive pipeline that propagates content changes from edited
Markdown files to browser DOM updates in milliseconds.

Purr targets Python 3.14+ with free-threading support and is designed for developers who
build content-driven sites — documentation, blogs, knowledge bases — and need a path from
static to dynamic without rewriting.

---

## 2. Problem Statement

### 2.1 The Gap

Every content tool forces a hard choice between static and dynamic:

| Approach | Tools | Limitation |
|----------|-------|-----------|
| Static site generator | Hugo, MkDocs, Sphinx, Astro | No dynamic features — need separate app |
| Web framework | Django, FastAPI, Flask | Overkill for content — no Markdown pipeline |
| Docs-as-a-service | Mintlify, Fern, GitBook | Vendor lock-in — can't extend or self-host |
| Hybrid (Next.js, Nuxt) | JS frameworks with SSG modes | Leaves the Python ecosystem entirely |

When a documentation site needs search, authentication, or a dashboard, the team rewrites
in a web framework. When a web application needs a content section, the team bolts on a
CMS. Neither transition is smooth because static and dynamic tools don't share content
models, templates, or deployment infrastructure.

### 2.2 Why Now

The Bengal ecosystem has solved each layer independently:

1. **Patitas** produces a typed, frozen AST from Markdown — content is a data structure,
   not a string. All nodes are `@dataclass(frozen=True, slots=True)`, hashable, comparable
   via `==`.

2. **Kida** compiles templates to Python AST with block-level dependency analysis —
   `block_metadata()` returns per-block context dependencies as `frozenset[str]`.
   `render_stream()` yields chunks at statement boundaries.

3. **Bengal** tracks file-level dependencies via EffectTracer — bidirectional dependency
   graph with transitive invalidation. `outputs_needing_rebuild(changed)` returns the
   exact set of affected outputs.

4. **Chirp** supports SSE fragment streaming — `EventStream` wraps an async generator,
   `Fragment` renders a named Kida block, htmx swaps fragments into the DOM.

5. **Pounce** serves with free-threading parallelism — thread-based workers sharing
   immutable state, with SSE connections handled natively.

These capabilities were designed independently but share the same architectural DNA. Purr
connects them.

### 2.3 Specific Gaps

1. **No content-to-browser reactive pipeline.** Bengal detects file changes and knows which
   pages are affected. Chirp can push SSE fragments. Nothing connects them — no AST diffing,
   no block-level change mapping, no targeted fragment delivery.

2. **No unified content + routes.** Bengal serves static content. Chirp serves dynamic
   routes. There's no way to combine them in a single URL space with shared templates and
   navigation.

3. **No progressive deployment model.** There's no tool that lets you start with static
   export and graduate to live server without rewriting content, templates, or routes.

4. **No Python content framework for the 2026 web.** MkDocs is static-only with no
   extensibility model. Sphinx is powerful but has a 2008 developer experience. There is
   no modern Python content platform that handles the spectrum from "I just want docs" to
   "I need docs plus dynamic features."

---

## 3. Target Users

### 3.1 Primary: Python Developers Building Content Sites

Developers who need documentation, blogs, or content-heavy sites and want to stay in the
Python ecosystem. Today they use MkDocs (limited) or Sphinx (painful) for content, and
switch to FastAPI/Django when they need dynamic features.

**Needs:**
- Markdown-based content pipeline with modern features (directives, syntax highlighting)
- Fast development loop (edit content → see changes instantly, no manual reload)
- Ability to add dynamic routes (search, API endpoints) without leaving the stack
- Static export for simple deployments, live server for dynamic features
- Python 3.14+ (early adopters of modern Python)

### 3.2 Secondary: Teams Outgrowing Static Site Generators

Teams whose documentation or content site has grown to need dynamic features — search,
authentication, dashboards, real-time updates — and are facing a rewrite to a web framework.

**Needs:**
- Migration path from pure static to static + dynamic without full rewrite
- Shared templates and navigation across static and dynamic pages
- Production deployment that handles both static content and dynamic routes
- Familiar Markdown-based authoring workflow

### 3.3 Tertiary: Bengal Ecosystem Users

Developers already using individual ecosystem libraries (Kida, Patitas, Rosettes, Chirp,
Pounce, Bengal) who want to see them work together as a unified platform.

**Needs:**
- Reference integration demonstrating the ecosystem's full potential
- Clear architecture for how the libraries compose
- The "demo" that makes the ecosystem story click

---

## 4. Functional Requirements

### 4.1 Three Modes (P0 — Must Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-001 | `purr dev` starts reactive dev server | Pounce server with file watcher, SSE broadcasting, auto-reload |
| F-002 | `purr build` exports static HTML | All content pages rendered to files, deployable to any CDN |
| F-003 | `purr serve` runs live production server | Static + dynamic routes served by Pounce with workers |
| F-004 | Same content/templates across all modes | Switching modes requires zero content changes |

### 4.2 Content Routing (P0 — Must Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-005 | Bengal pages served as Chirp routes | Each Bengal page has a URL handled by Chirp |
| F-006 | Pages rendered through Kida templates | Bengal's template context passed to Kida via Chirp integration |
| F-007 | Static assets served alongside content | CSS, JS, images available at configured static URL |
| F-008 | Frozen PurrConfig | `@dataclass(frozen=True, slots=True)`, immutable at runtime |
| F-009 | CLI entry point | `purr dev`, `purr build`, `purr serve` via argparse |
| F-010 | `purr.yaml` configuration | Site root, mode defaults, route declarations |

### 4.3 Reactive Pipeline (P0 — Must Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-011 | File change detection | Watcher detects content, template, config, asset changes |
| F-012 | Selective content re-parse | Only changed Markdown files re-parsed through Patitas |
| F-013 | AST diffing | Compare old/new Patitas ASTs, produce typed `ASTChange` set |
| F-014 | Block-level change mapping | Map AST changes to affected Kida template blocks |
| F-015 | Targeted SSE fragment push | Push only affected blocks via Chirp EventStream |
| F-016 | Cascade handling | Config changes propagate to nav/header blocks across all pages |
| F-017 | Template change handling | Template changes trigger full page refresh for affected pages |
| F-018 | Client-side SSE integration | Minimal JS or htmx snippet injected in dev mode |

### 4.4 Dynamic Routes (P1 — Should Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-019 | User-defined Chirp routes | Python functions in `routes/` served alongside content |
| F-020 | Shared template context | Dynamic routes access Bengal `site` model |
| F-021 | Navigation integration | Dynamic pages appear in site navigation |
| F-022 | Route auto-discovery | Routes loaded from configured directory without manual registration |

### 4.5 Static Export (P1 — Should Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-023 | Content page export | All Bengal pages rendered to HTML files |
| F-024 | Dynamic route pre-rendering | Chirp routes pre-rendered with default state |
| F-025 | Asset handling | Static assets copied to output directory |
| F-026 | `purr build` parity with Bengal | Content-only sites produce identical output to `bengal build` |

### 4.6 Developer Experience (P2 — Nice to Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| F-027 | `purr init` scaffolding | Generate project structure with content, templates, config |
| F-028 | Startup banner | Clear status: pages loaded, templates compiled, graph edges |
| F-029 | Change log in dev mode | Terminal shows affected blocks and push latency per change |
| F-030 | Error overlay | Render errors displayed as styled HTML in browser (dev mode) |
| F-031 | Default theme | Production-quality default theme for content sites |

---

## 5. Non-Functional Requirements

### 5.1 Performance

| ID | Requirement | Target |
|----|-------------|--------|
| NF-001 | Reactive pipeline latency | < 100ms from file save to browser update |
| NF-002 | Content re-parse (single file) | < 10ms for a typical Markdown page |
| NF-003 | Block re-render (single block) | < 5ms for a typical template block |
| NF-004 | Startup time (50-page site) | < 2 seconds to first request |
| NF-005 | Static export (50-page site) | < 5 seconds |
| NF-006 | Memory baseline | < 50MB RSS for a 50-page site in dev mode |

### 5.2 Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| NF-007 | No data races | Zero race conditions under concurrent load on 3.14t |
| NF-008 | Graceful degradation | Over-scoped changes fall back to full page refresh |
| NF-009 | SSE resilience | Disconnected clients cleaned up, no resource leaks |
| NF-010 | Content errors | Parse errors produce clear messages, don't crash server |

### 5.3 Developer Experience

| ID | Requirement | Target |
|----|-------------|--------|
| NF-011 | Zero-config for content sites | `purr dev` works in any Bengal-compatible directory |
| NF-012 | Type checker clean | Zero `type: ignore` in purr code |
| NF-013 | Meaningful errors | Missing templates, bad config, route conflicts produce clear messages |
| NF-014 | Add dynamic route friction | One Python file + one config line, no rewrite |

### 5.4 Compatibility

| ID | Requirement | Target |
|----|-------------|--------|
| NF-015 | Python version | >= 3.14 |
| NF-016 | Free-threading | Full support for 3.14t |
| NF-017 | Bengal compatibility | Any Bengal site is a valid Purr project |
| NF-018 | Platforms | Linux, macOS. Windows best-effort. |

---

## 6. Dependency Budget

### Core (always installed)

| Dependency | Purpose | Justification |
|------------|---------|---------------|
| bengal | Content pipeline, dependency tracking | Purr is the integration layer for Bengal |
| chirp | Web framework, SSE, fragments | Request handling and reactive delivery |
| pounce | ASGI server | Production serving with free-threading |

Bengal, Chirp, and Pounce transitively bring in Kida, Patitas, Rosettes, h11, anyio. Purr
adds zero additional runtime dependencies.

### Excluded

| Dependency | Reason |
|------------|--------|
| watchfiles | Bengal already includes file watching |
| htmx | Injected as a `<script>` tag, not a Python dependency |
| Any JS build tool | Purr is server-rendered HTML, no bundling |

---

## 7. Success Criteria

### 7.1 Phase 1: Content Router ✓

- [x] `purr dev` starts a Pounce server serving Bengal content via Chirp
- [x] Content pages rendered through Kida templates
- [x] `purr build` produces static output via Bengal's BuildOrchestrator
- [x] Static assets served alongside content
- [x] CLI works: `purr dev my-site/`, `purr build my-site/`, `purr serve my-site/`

### 7.2 Phase 2: Reactive Pipeline

- [ ] File save → browser update in < 100ms for a content change
- [ ] AST differ produces correct changesets for add/remove/modify
- [ ] Reactive mapper correctly identifies affected template blocks
- [ ] SSE broadcasts targeted fragments (not full pages)
- [ ] Cascade changes (config, nav) handled correctly
- [ ] Template changes trigger full page refresh

### 7.3 Phase 3: Dynamic Routes

- [ ] User-defined Chirp routes served alongside Bengal content
- [ ] Dynamic routes share template context with content pages
- [ ] `purr serve` runs in production with Pounce workers
- [ ] Mixed static + dynamic example works end-to-end

### 7.4 Phase 4: Static Export

- [ ] All routes (static + dynamic) exported to HTML files
- [ ] Exported site is byte-identical to live rendering for static pages
- [ ] Dynamic routes pre-rendered with default state

---

## 8. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| AST differ misidentifies changes | Wrong blocks updated or stale content | Medium | Conservative mapping (over-identify, never under-identify); fall back to full refresh on uncertainty |
| Content-to-context mapping is incomplete | Some content changes don't trigger updates | Medium | Start with coarse mapping (any body change → content block); refine over time |
| Reactive pipeline latency exceeds 100ms | Perceptible delay undermines the value proposition | Low | Profile each step independently; Patitas re-parse and Kida block render are both < 10ms in isolation |
| Bengal EffectTracer API changes | Integration breaks on Bengal updates | Low | Pin ecosystem versions; coordinated releases across repos |
| Chirp SSE can't handle concurrent page subscribers | Scalability issue in dev mode | Low | Dev mode is single-user; production subscribers are per-worker via Pounce threads |
| htmx swap causes layout flicker | Poor UX on reactive updates | Medium | Use htmx `hx-swap="morph"` for smooth transitions; test with CSS transitions |
| Scope creep toward "full framework" | Dilutes focus, duplicates Chirp/Bengal | High | Non-goals list enforced; Purr only integrates, never reimplements |

---

## 9. Out of Scope

Purr deliberately does not:

- **Duplicate ecosystem functionality.** Parsing is Patitas. Templates are Kida. Routing is
  Chirp. Serving is Pounce. Building is Bengal. Purr integrates, it doesn't reimplement.
- **Include a database layer.** Use databases directly in Chirp routes if needed.
- **Include a JavaScript build pipeline.** No bundling, transpiling, or Node.js.
- **Include authentication/authorization.** Handled by Chirp middleware.
- **Include a visual editor.** Content manipulation UI is a future product opportunity.
- **Be a hosting platform.** Managed hosting is a separate product concern.
- **Support Python < 3.14.** Ecosystem-wide requirement.
- **Compete with general-purpose frameworks.** Django, FastAPI, and Rails solve different
  problems.

---

## 10. Open Questions

1. **Should `purr.yaml` be a new config format or extend `bengal.yaml`?** Purr needs to
   know about routes, modes, and Chirp config in addition to Bengal's content config. Options:
   (a) extend Bengal's config with a `purr:` section, (b) separate `purr.yaml` that imports
   Bengal config, (c) `purr.yaml` as the superset that includes Bengal fields. Leaning toward
   (c) — Purr is the top-level tool.

2. **How fine-grained should the AST differ be?** Options: (a) node-level diff (every
   paragraph, heading, list item tracked individually), (b) section-level diff (content
   grouped by heading), (c) file-level diff (any change → re-render all content blocks).
   Start with (c) for simplicity, refine to (a) as the reactive mapper matures.

3. **Should the SSE snippet be htmx-based or custom JS?** htmx supports SSE natively via
   `hx-ext="sse"`. Custom JS would be smaller (~20 lines) and avoid the htmx dependency.
   Leaning toward htmx since Chirp already integrates with it.

4. **How should `purr serve` handle sites with no dynamic routes?** Options: (a) serve
   pre-rendered static files from memory (fast, no re-rendering), (b) render on every
   request through Kida (consistent, handles template changes), (c) hybrid (serve from
   memory, invalidate on file change). Leaning toward (a) for production, (b) for dev.

5. **Should Purr support themes?** A theme system would provide default templates,
   styles, and layouts. This is critical for adoption (first-five-minutes experience) but
   adds complexity. Defer to Phase 5 but design the template loader to support it.
