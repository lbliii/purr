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

**Status:** Pre-alpha — Phase 2 (reactive pipeline) complete. Content changes propagate
through AST diffing, dependency graph, and SSE broadcasting to the browser in milliseconds.
See [ROADMAP.md](ROADMAP.md) for the full plan.

## Quick Start

```bash
# Development server (single worker, debug mode)
purr dev my-site/

# Static export (delegates to Bengal's build pipeline)
purr build my-site/

# Production server (multi-worker via Pounce)
purr serve my-site/ --workers 4
```

Or programmatically:

```python
import purr

purr.dev("my-site/")       # Reactive local development
purr.build("my-site/")     # Static export
purr.serve("my-site/")     # Live production server
```

## Key Ideas

- **Content-reactive.** Content is a typed data structure, not a build artifact. Changes
  propagate through the AST, the dependency graph, the template compiler, and into the
  browser via SSE — surgically, in milliseconds.
- **Static-to-dynamic continuum.** Start with Markdown and templates. Add Chirp routes when
  you need search, APIs, or dashboards. Same templates, same server, same URL space. No
  migration, no rewrite.
- **Three modes.** `purr dev` for reactive local development. `purr build` for static
  export to any CDN. `purr serve` for live production with dynamic routes and real-time
  updates.
- **Integration layer.** Purr is thin by design — the hard problems are solved by Bengal
  (content pipeline), Chirp (framework), Kida (templates), Patitas (Markdown), Rosettes
  (highlighting), and Pounce (server). Purr wires them together.
- **Free-threading native.** Built on Python 3.14t. Pounce serves with real thread
  parallelism. Kida compiles templates to Python AST. Patitas parses Markdown with O(n)
  state machines. No GIL, no fork, no compromise.

## Requirements

- Python >= 3.14

## Part of the Bengal Ecosystem

```
purr        Content runtime   (connects everything)
pounce      ASGI server       (serves apps)
chirp       Web framework     (serves HTML)
kida        Template engine   (renders HTML)
patitas     Markdown parser   (parses content)
rosettes    Syntax highlighter (highlights code)
bengal      Static site gen   (builds sites)
```

## License

MIT
