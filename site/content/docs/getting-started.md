---
title: Getting Started
description: Set up your first Purr site in minutes
tags:
  - quickstart
  - tutorial
---

## Installation

```bash
uv add bengal-purr
```

hihihi

## Create a Site

Create a directory with some Markdown content:

```
my-site/
  content/
    _index.md        # Home page
    docs/
      _index.md      # Section index
      guide.md       # Content page
  routes/            # Optional dynamic routes
    search.py
```

## Run Dev Server

```bash
purr dev my-site/
```

This starts the content-reactive development server:

- **File watcher** detects changes to content, templates, and config
- **Incremental parsing** via Patitas re-parses only the changed region
- **AST diffing** identifies exactly which blocks changed
- **Reactive mapper** maps AST changes to template blocks
- **SSE broadcasting** pushes targeted fragment updates to the browser

No full page reload needed. Just edit and watch.

## Build for Production

```bash
purr build my-site/
```

Exports everything as static HTML to `dist/`. Deploy anywhere: CDN, GitHub Pages, S3, Netlify.

## Serve Live

```bash
purr serve my-site/
```

Runs a production Pounce server with multi-worker support. Static content and dynamic routes coexist in a unified URL space.

## Dynamic Routes

Drop a Python file in `routes/` to add server-side logic:

```python
# routes/search.py
from chirp import Template

async def get(request):
    query = request.query.get("q", "")
    results = purr.site.search(query)
    return Template("search.html", query=query, results=results)
```

Dynamic routes are discovered at startup and coexist with content pages.
