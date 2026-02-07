# Architecture Design Document: Purr

**Version**: 0.1.0-dev
**Date**: 2026-02-07
**Status**: Phase 2 — reactive pipeline complete

---

## 1. Architectural Goals

1. **Content-reactive by construction.** Content changes propagate through a typed pipeline
   — AST diff, dependency graph, template blocks, SSE fragments — with every step traceable
   and every intermediate result typed.

2. **Integration, not reimplementation.** Purr adds no new parsing, templating, routing, or
   serving capabilities. It exclusively wires together Bengal, Chirp, Kida, Patitas, Rosettes,
   and Pounce. New code is limited to the glue: diffing, mapping, broadcasting, and routing.

3. **Free-threading by inheritance.** All ecosystem libraries are free-threading safe. Purr
   maintains this by using frozen data structures, ContextVar isolation, and per-worker
   state. No new shared mutable state.

4. **Typed end-to-end.** Zero `type: ignore` comments. Every internal interface has complete
   type annotations. The type checker (`ty`) is a first-class development tool.

5. **Three modes, one codebase.** `dev`, `build`, and `serve` use the same content pipeline,
   templates, and configuration. Mode selection determines deployment (local server, static
   files, or production server), not application structure.

6. **Thin by design.** Purr's total codebase should remain under 5,000 lines of application
   code (excluding tests and docs). If a component grows beyond glue code, it belongs in one
   of the ecosystem libraries.

---

## 2. System Context

```
    ┌──────────────────────────────────────────────────────────┐
    │                        Browser                           │
    │  (htmx SSE subscription on /__purr/events)              │
    └───────────────────────────┬──────────────────────────────┘
                                │ HTTP + SSE
    ┌───────────────────────────▼──────────────────────────────┐
    │                        Pounce                            │
    │  (ASGI server, free-threading workers)                   │
    └───────────────────────────┬──────────────────────────────┘
                                │ ASGI protocol
    ┌───────────────────────────▼──────────────────────────────┐
    │                      Purr App                            │
    │                                                          │
    │  ┌────────────────────────────────────────────────────┐  │
    │  │              Content Router                        │  │
    │  │  Bengal pages → Chirp routes                       │  │
    │  │  User routes → Chirp routes                       │  │
    │  │  SSE endpoint → /__purr/events                     │  │
    │  └──────────────────────┬─────────────────────────────┘  │
    │                         │                                │
    │  ┌──────────────────────▼─────────────────────────────┐  │
    │  │           Reactive Pipeline (dev mode)             │  │
    │  │                                                    │  │
    │  │  Watcher → Differ → Mapper → Broadcaster          │  │
    │  │  (files)   (AST)    (blocks)  (SSE)               │  │
    │  └────────────────────────────────────────────────────┘  │
    │                                                          │
    └──────────────────────────────────────────────────────────┘
                                │
          ┌─────────────────────┼──────────────────────┐
          │                     │                      │
    ┌─────▼─────┐        ┌─────▼─────┐         ┌─────▼─────┐
    │  Bengal    │        │  Chirp    │         │  Kida     │
    │  (content │        │  (HTTP,   │         │  (compile,│
    │   pipeline,│       │   SSE,    │         │   render, │
    │   effects) │        │   routes) │         │   analyze)│
    └───────────┘        └───────────┘         └───────────┘
          │                                          │
    ┌─────▼─────┐                              ┌─────▼─────┐
    │  Patitas  │                              │  Rosettes │
    │  (parse   │                              │  (syntax  │
    │   markdown)│                             │   highlight│
    └───────────┘                              └───────────┘
```

---

## 3. Layer Architecture

Purr is organized into four layers. Each layer depends only on layers below it. No upward
dependencies. No circular imports.

### 3.1 Interface Layer

**Purpose:** Entry points — CLI, programmatic API, configuration.

**Components:**
- `purr.dev()`, `purr.build()`, `purr.serve()` — programmatic entry points
- `purr._cli` — argparse-based CLI
- `PurrConfig` — frozen configuration dataclass

**Constraints:**
- Translates user input into `PurrConfig` and a mode selection
- No content or reactive logic in this layer

### 3.2 Application Layer

**Purpose:** The unified content + routes application.

**Components:**
- `PurrApp` — wraps a Bengal `Site` and a Chirp `App` into one ASGI callable
- `ContentRouter` — maps Bengal pages to Chirp routes
- User route loader — discovers and registers `routes/*.py` handlers

**Constraints:**
- Owns the URL space (merging content routes and user routes)
- Owns the template context (extending Bengal's page context for Chirp rendering)
- Does not own content parsing, template rendering, or HTTP handling

### 3.3 Reactive Layer

**Purpose:** Change detection, propagation, and delivery.

**Components:**
- `ContentWatcher` — file change detection via watchfiles
- `ASTDiffer` — structural diff on Patitas frozen ASTs
- `DependencyGraph` — unified file-level + block-level dependency tracking
- `ReactiveMapper` — maps AST changes to affected template blocks
- `Broadcaster` — SSE delivery of rendered fragments to connected clients

**Constraints:**
- Only active in `dev` and `serve` modes (not `build`)
- Each component is independently testable
- The pipeline is unidirectional: watch → diff → map → render → push

### 3.4 Export Layer

**Purpose:** Static file output.

**Components:**
- `StaticExporter` — renders all routes to HTML files
- Asset copier — copies static assets to output directory

**Constraints:**
- Only active in `build` mode
- Output must match live rendering for content pages
- Dynamic routes pre-rendered with default state

---

## 4. Component Design

### 4.1 PurrApp Lifecycle

```
    ┌─────────┐     ┌──────────┐     ┌────────┐     ┌─────────┐
    │  LOAD   │────>│ COMPILE  │────>│ FROZEN │────>│ SERVING │
    └─────────┘     └──────────┘     └────────┘     └─────────┘

    Read purr.yaml   Load Bengal site  Route table     Dev: watch + SSE
    Parse config      Register routes   is immutable    Build: export
                      Compile Kida env  Dep graph built Serve: production
```

**Load phase:** Read `purr.yaml`, resolve paths, create `PurrConfig`. Discover content
files via Bengal's content discovery. Discover user routes in `routes/` directory.

**Compile phase:** Parse all content through Patitas (via Bengal). Compile all templates
through Kida (via Bengal/Chirp). Build the unified dependency graph. Register content pages
and user routes as Chirp routes. Freeze the Chirp app.

**Frozen phase:** The compiled state is immutable. Route table, dependency graph, template
environment, and config cannot change. This is the state that serves requests.

**Serving phase:** Mode-dependent:
- `dev` — Pounce single-worker, file watcher active, SSE broadcasting
- `build` — render all routes to files, exit
- `serve` — Pounce multi-worker, SSE broadcasting, no file watcher

### 4.2 Content Routing Flow

```
    Bengal discovers content files
           │
           ▼
    ┌──────────────┐
    │ ContentRouter │  For each page in site.pages:
    │               │    register Chirp route at page.permalink
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ User Routes  │  For each module in routes/:
    │  (optional)  │    register Chirp route at configured path
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ SSE Endpoint │  Register /__purr/events for reactive updates
    │  (dev/serve) │  (skipped in build mode)
    └──────┬───────┘
           │
           ▼
    Chirp App is frozen — route table compiled
```

### 4.3 Reactive Pipeline Flow

```
    ┌─────────────────┐
    │  File Change     │  watchfiles detects modification
    │  (ContentWatcher)│
    └────────┬────────┘
             │ categorize: content | template | config | asset
             │
    ┌────────▼────────┐
    │ Content Change   │─────────────────────────┐
    │                  │                          │
    │ Re-parse via     │  Template Change         │  Config Change
    │ Patitas          │  ──────────────          │  ─────────────
    └────────┬────────┘  Recompile template       │  Full cascade:
             │            via Kida. Find affected  │  find all pages
             │            pages via Bengal          │  depending on
             │            EffectTracer. Push full   │  changed config.
             │            page refresh for each.    │  Re-render
             │                                      │  nav/header blocks
    ┌────────▼────────┐                             │  for all.
    │ AST Diff         │                             │
    │ (ASTDiffer)      │  Compare old AST ↔ new AST │
    │                  │  using frozen node equality  │
    └────────┬────────┘                              │
             │ ASTChange[]                           │
             │                                       │
    ┌────────▼────────┐                              │
    │ Block Mapping    │◄────────────────────────────┘
    │ (ReactiveMapper) │
    │                  │  Map changes to Kida blocks:
    │                  │  ASTChange → context path → block_metadata()
    └────────┬────────┘
             │ set[BlockName]
             │
    ┌────────▼────────┐
    │ Re-render        │  Kida render_block() for each affected block
    │ (Kida)           │  using updated page context
    └────────┬────────┘
             │ Fragment[]
             │
    ┌────────▼────────┐
    │ Broadcast        │  Push Chirp Fragment via SSE
    │ (Broadcaster)    │  to clients subscribed to this page
    └─────────────────┘
```

### 4.4 AST Differ Design

Patitas AST nodes are `@dataclass(frozen=True, slots=True)`. This gives us:

- **Hashable:** Nodes can be used in sets and dicts.
- **Comparable:** `node_a == node_b` compares recursively through children.
- **Positioned:** Every node has a `SourceLocation` with line/column/offset.

The differ exploits these properties:

```python
def diff_documents(old: Document, new: Document) -> tuple[ASTChange, ...]:
    """Structural diff on two Patitas Document trees.

    Algorithm:
    1. Walk both trees in parallel by child index
    2. For each position, compare nodes via ==
    3. If equal, skip the subtree (fast path — frozen nodes)
    4. If different types, emit removed + added
    5. If same type but different content, emit modified
    6. Handle length mismatches (trailing adds/removes)

    This is NOT a generic tree edit distance (which is NP-hard).
    It's a positional diff on a known schema where children are
    ordered tuples, not arbitrary sets.
    """
```

**Complexity:** O(n) where n is the number of nodes that differ. Unchanged subtrees are
skipped in O(1) via `==` on frozen nodes (Python short-circuits on identity first, then
compares recursively).

### 4.5 Reactive Mapper Design

The mapper connects three type systems:

1. **Patitas AST node types** — what changed in the content
2. **Bengal template context** — how content is presented to templates
3. **Kida block metadata** — which blocks depend on which context variables

```
    AST Change                Context Path              Template Block
    ──────────                ────────────              ──────────────
    Heading modified    →     page.toc changed    →     "sidebar" block
    Paragraph modified  →     page.body changed   →     "content" block
    FrontMatter changed →     page.title changed  →     "header" block
    Any content change  →     page.* changed      →     all page-dependent blocks
```

The content-to-context mapping is defined by Bengal's content model — how it transforms a
Patitas AST into the dict that Kida receives. The block-to-context mapping comes from
Kida's `block_metadata()`, which returns `frozenset[str]` of context paths per block.

The mapper is conservative: it may over-identify affected blocks (causing unnecessary
re-renders) but never under-identifies (causing stale content). When in doubt, re-render
the block.

### 4.6 Broadcaster Design

```
    ┌─────────────────────────────────────────┐
    │              Broadcaster                │
    │                                         │
    │  subscribers: dict[permalink, set[SSE]] │
    │  _lock: threading.Lock                  │
    │                                         │
    │  subscribe(permalink) → SSE connection  │
    │  unsubscribe(permalink, conn)           │
    │  push(permalink, fragments)             │
    └─────────────────────────────────────────┘
```

Each browser tab viewing a Purr page subscribes to `/__purr/events?page=/current/path`.
The broadcaster maintains a map of page permalinks to active SSE connections.

When the reactive mapper produces affected blocks, the broadcaster:

1. Re-renders each block via Kida's `render_block()` with the updated page context
2. Wraps each as a Chirp `Fragment`
3. Pushes to all clients subscribed to the affected page

**Thread safety:** The subscriber map is protected by a `threading.Lock`. In dev mode
(single worker), contention is zero. In serve mode (multi-worker), each worker has its own
broadcaster instance — no cross-worker state.

### 4.7 Static Export Design

```
    PurrApp (frozen, all routes registered)
           │
           ▼
    ┌──────────────┐
    │ StaticExporter│  Iterate all routes (content + dynamic)
    └──────┬───────┘
           │
           ├── Content route:
           │   Render page through Kida (same path as live)
           │   Write to output/permalink/index.html
           │
           ├── Dynamic route:
           │   Simulate request with default params
           │   Render response
           │   Write to output/path/index.html
           │
           └── Static assets:
               Copy from static/ to output/static/
               Optional fingerprinting (hash in filename)
```

---

## 5. Thread Safety Architecture

### 5.1 Immutability Categories

| Component | Mutability | Phase | Mechanism |
|-----------|-----------|-------|-----------|
| PurrConfig | Immutable | Always | `@dataclass(frozen=True, slots=True)` |
| Bengal Site model | Immutable | After load | Frozen page/section objects |
| Chirp route table | Immutable | After freeze | Compiled router |
| Kida environment | Immutable | After freeze | Copy-on-write internals |
| Dependency graph | Immutable | After compile | Frozen edges and lookup tables |
| Broadcaster subscribers | Mutable | Per-worker | `threading.Lock` protected |
| AST cache (old ASTs) | Mutable | Per-worker | `dict[Path, Document]`, single-writer |

### 5.2 What Has No Locks

- Content routing (reads frozen route table)
- Template rendering (Kida is thread-safe)
- AST diffing (pure function on frozen inputs)
- Block mapping (reads frozen dependency graph + frozen block metadata)
- Config access (frozen dataclass)

### 5.3 What Needs Care

- **Broadcaster subscriber map:** Multiple clients connecting/disconnecting concurrently.
  Protected by a per-worker `threading.Lock`. In dev mode (single worker), this is
  uncontended.

- **AST cache for diffing:** The watcher stores the previous AST for each content file to
  diff against the new parse. This is single-writer (the watcher) but could be read during
  a concurrent re-parse. Use a simple dict with replace-on-write semantics (dict assignment
  is atomic in CPython).

- **File watcher shutdown:** The watcher runs in a background thread/task. Shutdown
  coordination uses `asyncio.Event` or `threading.Event` to signal the watcher to stop.

---

## 6. Module Dependency Graph

```
    purr/__init__.py  (public API: dev, build, serve, PurrConfig)
           │
           │  ── Primitives (leaf nodes, no internal deps) ──────────
           │
           ├── purr/config.py            (no internal deps; PurrConfig)
           ├── purr/_types.py            (no internal deps; type aliases)
           ├── purr/_errors.py           (no internal deps; PurrError hierarchy)
           │
           │  ── Content Layer ──────────────────────────────────────
           │
           ├── purr/content/
           │      ├── router.py          (external: bengal, chirp; depends on config.py)
           │      ├── watcher.py         (external: watchfiles; depends on _types.py)
           │      └── differ.py          (external: patitas; depends on _types.py, _errors.py)
           │
           │  ── Reactive Layer ─────────────────────────────────────
           │
           ├── purr/reactive/
           │      ├── graph.py           (external: bengal, kida; depends on _types.py)
           │      ├── mapper.py          (depends on graph.py, content/differ.py)
           │      └── broadcaster.py     (external: chirp; depends on _types.py, mapper.py)
           │
           │  ── Export Layer ───────────────────────────────────────
           │
           ├── purr/export/
           │      └── static.py          (depends on config.py; external: bengal)
           │
           │  ── Application Layer ──────────────────────────────────
           │
           ├── purr/app.py               (depends on config.py, content/, reactive/, export/)
           └── purr/_cli.py              (depends on app.py, config.py)
```

**Key constraints:**
- Primitives (`config.py`, `_types.py`, `_errors.py`) have no internal dependencies.
- Content layer depends only on primitives and ecosystem libraries.
- Reactive layer depends on content layer (differ) and ecosystem libraries.
- Application layer depends on everything below it.
- No circular imports. Dependency direction is strictly downward.

---

## 7. Decisions and Trade-offs

### 7.1 Integration Layer, Not a Framework

**Decision:** Purr adds no new HTTP, template, or content capabilities. It is strictly an
integration layer.

**Rationale:** The ecosystem libraries are well-tested and well-designed. Reimplementing
any of their functionality would create maintenance burden and divergence risk. Purr's value
is in the wiring, not the components.

**Trade-off:** Purr is tightly coupled to the ecosystem's APIs. If Bengal's EffectTracer
changes, Purr breaks. Mitigated by coordinated releases and version pinning.

### 7.2 Conservative Reactive Mapping

**Decision:** The reactive mapper over-identifies affected blocks rather than risking stale
content. When uncertain, it triggers a full page refresh.

**Rationale:** Stale content in the browser is worse than an unnecessary re-render. The
development experience should feel reliable even if it's occasionally less surgical than
theoretically possible.

**Trade-off:** Some changes will trigger broader updates than necessary. This is acceptable
because the rendering cost is low (Kida block renders in < 5ms) and the alternative (stale
content) undermines trust.

### 7.3 Positional AST Diff, Not Edit Distance

**Decision:** The AST differ uses positional comparison (walk trees by child index), not
generic tree edit distance.

**Rationale:** Generic tree edit distance is NP-hard. Markdown documents have ordered
children (paragraphs, headings, lists in sequence), so positional comparison is both correct
and fast. Inserting a paragraph shifts subsequent positions, which the differ handles as
modify + trailing adds.

**Trade-off:** Moving a section (cut paragraph from position 3, paste at position 7) appears
as a delete + add rather than a move. This is fine — both old and new positions get updated.

### 7.4 htmx for Client-Side SSE

**Decision:** Use htmx's SSE extension for client-side fragment swapping rather than custom
JavaScript.

**Rationale:** Chirp already integrates with htmx (`request.is_fragment`, `Fragment` return
type). htmx's `hx-ext="sse"` provides SSE subscription, event filtering, and DOM swapping
in a declarative way. Writing custom JS would replicate htmx's functionality for no benefit.

**Trade-off:** htmx (~14KB gzipped) is included in dev mode pages. Acceptable given its
utility and the fact that Chirp users likely already use it.

### 7.5 Per-Worker Broadcaster (No Cross-Worker State)

**Decision:** Each Pounce worker has its own Broadcaster instance. No shared subscriber
state across workers.

**Rationale:** Cross-worker state requires IPC (queues, shared memory, or a message bus),
which adds complexity and latency. In dev mode, there's one worker. In serve mode, each
worker handles its own SSE connections independently — a client connects to one worker and
stays there (TCP affinity).

**Trade-off:** A content change detected by the file watcher must propagate to all workers.
In dev mode (single worker), this is trivial. In serve mode, the watcher runs in the main
thread and signals all workers via their event loops. This requires a
`loop.call_soon_threadsafe()` bridge, which Pounce already implements for shutdown
coordination.

---

## 8. Observability

### 8.1 Startup Banner

```
Purr v0.1.0 — content-reactive runtime
─────────────────────────────────────────
✓ Loaded 12 pages, 3 sections
✓ Compiled 5 templates (Kida)
✓ Built dependency graph (47 edges)
✓ Live mode active — SSE broadcasting on /__purr/events

→ http://localhost:3000

Watching for changes...
```

### 8.2 Change Log (Dev Mode)

```
✦ content/docs/getting-started.md changed
  AST diff: 1 modified node (Paragraph at line 14)
  Affected blocks: ["content"] (via page.body)
  Pushed fragment to 1 client — 3ms

✦ templates/page.html changed
  Template recompiled — 2ms
  Affected pages: 9 (via extends base.html → page.html)
  Full page refresh pushed to 1 client

✦ purr.yaml changed
  Affected: site.title → 12 pages (block: "header")
  Pushed fragment to 1 client — 8ms (12 blocks batched)
```

### 8.3 Error Reporting

Content parsing errors, template compilation errors, and route loading errors produce clear
messages with file paths, line numbers, and fix suggestions. Errors don't crash the server
— the affected page shows an error overlay in dev mode and returns 500 in serve mode.

---

## 9. Testing Strategy

### 9.1 Unit Tests (Content Layer)

- AST differ: given two Documents, assert correct ASTChange set
- Content router: given a Bengal Site, assert correct Chirp routes
- Config: frozen, path resolution, defaults

### 9.2 Unit Tests (Reactive Layer)

- Reactive mapper: given ASTChanges + block metadata, assert correct block set
- Dependency graph: given file changes, assert correct transitive outputs
- Broadcaster: subscribe, unsubscribe, push to correct subscribers

### 9.3 Integration Tests

- Full pipeline: edit Markdown file → assert SSE event received with correct fragment
- Content routing: start PurrApp, request page, assert rendered HTML
- Static export: build site, assert output matches live rendering
- Mixed routes: content + dynamic routes, assert both work with shared templates

### 9.4 Property-Based Tests (Hypothesis)

- AST differ: for any two Documents, diff is consistent (apply changes to old → equals new)
- Reactive mapper: for any content change, affected blocks is a superset of actually changed blocks (conservative guarantee)

---

## 10. Ecosystem Dependencies

| Capability | Library | API Used | Status |
|-----------|---------|----------|--------|
| Content discovery | Bengal | `Site.pages`, `Site.sections` | Available |
| File-level deps | Bengal | `EffectTracer.outputs_needing_rebuild()` | Available |
| Incremental state | Bengal | `BuildCache.get_affected_pages()` | Available |
| Markdown parsing | Patitas | `parse(source) → Document` | Available |
| Typed frozen AST | Patitas | `Document`, `Block`, `Inline` nodes | Available |
| Template compilation | Kida | `Environment.get_template()` | Available |
| Block rendering | Kida | `Template.render_block(name, **ctx)` | Available |
| Block deps analysis | Kida | `Template.block_metadata()` | Available |
| Template deps | Kida | `Template.depends_on()` | Available |
| Streaming render | Kida | `Template.render_stream(**ctx)` | Available |
| HTTP routing | Chirp | `App.route()`, `Router` | Available |
| SSE streaming | Chirp | `EventStream`, `Fragment`, `SSEEvent` | Available |
| Fragment rendering | Chirp | `render_fragment()` | Available |
| ASGI serving | Pounce | `pounce.run()`, `ServerConfig` | Available |
| Free-threading | Pounce | Thread-based workers | Available |
| Syntax highlighting | Rosettes | Via Patitas integration | Available |
| AST diffing | Purr | `diff_documents()` | Built |
| Content-to-block mapping | Purr | `ReactiveMapper` | Built |
| SSE broadcasting | Purr | `Broadcaster` | Built |
