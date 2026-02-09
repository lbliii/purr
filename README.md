# purr

A content-reactive runtime for Python 3.14t.

```python
import purr

purr.dev("my-site/")
```

Purr unifies the Bengal ecosystem into a single content-reactive runtime. Edit a Markdown
file, and the browser updates the affected paragraph — not the page, not the site, just the
content that changed. Add a dynamic route alongside your static content without changing
frameworks. Deploy as static files or run as a live server. The boundary between static
site and web application disappears.

**Status:** Pre-alpha — Phase 5 (incremental pipeline + observability) complete. Content
changes propagate in O(change): incremental re-parse, selective block recompile, and
targeted SSE broadcast. Full-stack observability unifies events from Pounce connections,
content parsing, template compilation, and browser updates into a single queryable log.
See [ROADMAP.md](ROADMAP.md) for the full plan.

---

## Why Purr?

Every existing content tool forces a choice: static site or web application.

Static site generators build HTML files from content — fast and deployable, but when you
need search, authentication, or a dashboard, you leave the static world and rewrite in a
framework. Web frameworks handle dynamic content natively, but they're overkill for
documentation and their content story is an afterthought.

The Bengal ecosystem already solves each piece: Patitas parses Markdown into typed ASTs,
Kida compiles templates to Python AST, Rosettes highlights code in O(n), Bengal builds
static sites with dependency tracking, Chirp serves HTML with SSE streaming, and Pounce
runs ASGI with real thread parallelism.

What was missing is the integration — the layer that connects Bengal's dependency graph to
Chirp's SSE pipeline, maps Patitas AST changes to Kida template blocks, and makes "static
site that becomes a dynamic app" a single command instead of a rewrite.

Purr is that layer.

---

## Quick Start

```bash
# Development server (single worker, reactive pipeline active)
purr dev my-site/

# Static export (renders all routes to HTML files)
purr build my-site/

# Static export with asset fingerprinting and sitemap
purr build my-site/ --base-url https://example.com --fingerprint

# Production server (multi-worker via Pounce)
purr serve my-site/ --workers 4
```

Or programmatically:

```python
import purr

purr.dev("my-site/")       # Reactive local development
purr.build("my-site/")     # Static export (all routes → HTML files)
purr.serve("my-site/")     # Live production server
```

---

## How It Works

Content is a reactive data structure, not a build artifact. When you edit a Markdown file,
the change propagates through a typed pipeline:

```
Edit Markdown file
    → Patitas incrementally re-parses only the affected blocks (O(change), not O(document))
    → ASTDiffer identifies which nodes changed (O(1) skip for unchanged subtrees)
    → DependencyGraph resolves affected pages and template blocks
    → Kida selectively recompiles only the changed template blocks (O(changed_blocks))
    → ReactiveMapper maps AST changes to specific block updates
    → Broadcaster pushes HTML fragments via SSE
    → Browser swaps the DOM (htmx, no JS framework)
    → Every step recorded as a typed event in the observability log
```

This isn't hot-reload. Hot-reload rebuilds the page. Purr traces a content change through
the dependency graph to the exact DOM element that needs updating — and every step is
observable.

```
┌─────────────────────────────────────────────────────────┐
│  Browser (htmx SSE subscription on /__purr/events)      │
└────────────────────────────┬────────────────────────────┘
                             │ HTTP + SSE
┌────────────────────────────▼────────────────────────────┐
│  Pounce (ASGI server, free-threading workers)           │
└────────────────────────────┬────────────────────────────┘
                             │ ASGI
┌────────────────────────────▼────────────────────────────┐
│  Purr App                                               │
│                                                         │
│  ContentRouter — Bengal pages as Chirp routes            │
│  RouteLoader  — user Python routes alongside content    │
│  SSE endpoint — /__purr/events                          │
│                                                         │
│  Reactive Pipeline (dev mode):                          │
│  FileWatcher → Incremental Parse → ASTDiffer → Mapper   │
│    → Block Recompile → SSE Broadcaster                  │
│                                                         │
│  Observability:                                         │
│  StackCollector ← Pounce events + pipeline events       │
│    → EventLog (queryable ring buffer)                   │
└─────────────────────────────────────────────────────────┘
```

---

## Dynamic Routes

Add Python routes alongside your static content. Create a file in `routes/` — the file
path becomes the URL, and function names map to HTTP methods:

```
my-site/
├── content/          # Markdown pages (served by Bengal)
├── routes/
│   ├── search.py     # GET /search
│   └── api/
│       └── users.py  # GET /api/users
└── templates/
```

```python
# routes/search.py
from chirp import Request, Response

async def get(request: Request) -> Response:
    query = request.query.get("q", "")
    results = site.search(query)
    return request.template("search.html", query=query, results=results)
```

No decorators. No base classes. No registration ceremony. If a function is named `get`,
`post`, `put`, `delete`, or `patch`, it handles that HTTP method. If it's named `handler`,
it handles GET.

Dynamic routes share the same templates and URL space as your content. They appear in
navigation automatically via `nav_title`, and they access the Bengal site data through
`from purr import site`.

---

## Key Ideas

- **Content-reactive.** Content is a typed data structure, not a build artifact. Changes
  propagate through incremental re-parse, AST diff, selective block recompile, and into
  the browser via SSE — surgically, in O(change), not O(document).
- **Static-to-dynamic continuum.** Start with Markdown and templates. Add Chirp routes when
  you need search, APIs, or dashboards. Same templates, same server, same URL space. No
  migration, no rewrite.
- **Three modes.** `purr dev` for reactive local development. `purr build` for static
  export to any CDN — renders all routes (content + dynamic), fingerprints assets, and
  generates a sitemap. `purr serve` for live production with dynamic routes and real-time
  updates.
- **Observable.** Every stage of the pipeline — connection, parse, diff, recompile,
  broadcast — produces a typed event with nanosecond timestamps. Query the `EventLog` by
  event type, file path, or time range. Full-stack telemetry without logging.
- **Integration layer.** Purr is thin by design — the hard problems are solved by Bengal
  (content pipeline), Chirp (framework), Kida (templates), Patitas (Markdown), Rosettes
  (highlighting), and Pounce (server). Purr wires them together.
- **Free-threading native.** Built on Python 3.14t. Pounce serves with real thread
  parallelism. Kida compiles templates to Python AST. Patitas parses Markdown with O(n)
  state machines. No GIL, no fork, no compromise.

---

## Requirements

- Python >= 3.14

---

## The Bengal Ecosystem

A structured reactive stack — every layer written in pure Python for 3.14t free-threading.

| | | | |
|--:|---|---|---|
| **ᓚᘏᗢ** | [Bengal](https://github.com/lbliii/bengal) | Static site generator | [Docs](https://lbliii.github.io/bengal/) |
| **∿∿** | **Purr** | Content runtime ← You are here | — |
| **⌁⌁** | [Chirp](https://github.com/lbliii/chirp) | Web framework | [Docs](https://lbliii.github.io/chirp/) |
| **⟩⟩·** | [Pounce](https://github.com/lbliii/pounce) | ASGI server | [Docs](https://lbliii.github.io/pounce/) |
| **)彡** | [Kida](https://github.com/lbliii/kida) | Template engine | [Docs](https://lbliii.github.io/kida/) |
| **ฅᨐฅ** | [Patitas](https://github.com/lbliii/patitas) | Markdown parser | [Docs](https://lbliii.github.io/patitas/) |
| **⌾⌾⌾** | [Rosettes](https://github.com/lbliii/rosettes) | Syntax highlighter | [Docs](https://lbliii.github.io/rosettes/) |

Python-native. Free-threading ready. No npm required.

---

## License

MIT
