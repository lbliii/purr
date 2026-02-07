# Technical Design Document: Purr Core Types and Protocols

**Version**: 0.1.0-dev
**Date**: 2026-02-07
**Status**: Phase 0 — scaffolding complete

---

## 1. Purpose

This document defines the concrete types, protocols, and interfaces that form Purr's core.
These are the building blocks that connect the ecosystem libraries into a reactive pipeline.

Purr is an integration layer — most types are thin wrappers or bridges between existing
ecosystem types. The genuinely new types are the AST differ, the reactive mapper, and the
broadcaster.

All code targets Python 3.14+ with free-threading support. All dataclasses use
`frozen=True, slots=True`. All type annotations use modern syntax (`X | None`, `list[str]`).

---

## 2. Configuration

### 2.1 PurrConfig

```python
# purr/config.py

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PurrConfig:
    """Configuration for a Purr application.

    Frozen after creation. All paths resolve relative to root.
    """

    root: Path = field(default_factory=Path.cwd)
    host: str = "127.0.0.1"
    port: int = 3000
    output: Path = field(default_factory=lambda: Path("dist"))
    workers: int = 0  # 0 = auto-detect via Pounce
    routes_dir: str = "routes"
    content_dir: str = "content"
    templates_dir: str = "templates"
    static_dir: str = "static"

    @property
    def content_path(self) -> Path:
        return self.root / self.content_dir

    @property
    def templates_path(self) -> Path:
        return self.root / self.templates_dir

    @property
    def static_path(self) -> Path:
        return self.root / self.static_dir

    @property
    def routes_path(self) -> Path:
        return self.root / self.routes_dir

    @property
    def output_path(self) -> Path:
        if self.output.is_absolute():
            return self.output
        return self.root / self.output
```

---

## 3. Error Hierarchy

```python
# purr/_errors.py

class PurrError(Exception):
    """Base error for all purr operations."""

class ConfigError(PurrError):
    """Invalid or missing configuration."""

class ContentError(PurrError):
    """Error in content processing (parsing, diffing, routing)."""

class ReactiveError(PurrError):
    """Error in the reactive pipeline (mapping, broadcasting)."""

class ExportError(PurrError):
    """Error during static export."""
```

---

## 4. Type Aliases

```python
# purr/_types.py

from pathlib import Path

# Mode of operation
type PurrMode = str  # "dev" | "build" | "serve"

# Content source file path
type ContentPath = Path

# Kida template block name
type BlockName = str

# SSE client identifier
type ClientID = str
```

---

## 5. AST Differ Types

### 5.1 ASTChange

The core output of the differ. Describes a single change between two Patitas Document trees.

```python
# purr/content/differ.py

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ASTChange:
    """A single change between two AST trees.

    Attributes:
        kind: Type of change.
        path: Position in the tree as a tuple of child indices.
            Example: (2, 0) means "third child of root, first child of that".
        old_node: The node before the change (None for additions).
        new_node: The node after the change (None for removals).
    """

    kind: Literal["added", "removed", "modified"]
    path: tuple[int, ...]
    old_node: object | None
    new_node: object | None
```

### 5.2 diff_documents

```python
# purr/content/differ.py (continued)

from patitas.nodes import Block, Document, Node


def diff_documents(old: Document, new: Document) -> tuple[ASTChange, ...]:
    """Structural diff on two Patitas Document trees.

    Returns a tuple of ASTChange objects describing the differences.
    Unchanged subtrees are skipped in O(1) via == on frozen nodes.

    Algorithm:
    - Walk both trees by child index (positional comparison)
    - Equal nodes (==) → skip subtree
    - Different types → removed + added
    - Same type, different content → modified
    - Length mismatch → trailing adds or removes
    """
    changes: list[ASTChange] = []
    _diff_children(old.children, new.children, (), changes)
    return tuple(changes)


def _diff_children(
    old_children: tuple[Block, ...],
    new_children: tuple[Block, ...],
    parent_path: tuple[int, ...],
    changes: list[ASTChange],
) -> None:
    """Recursively diff ordered child tuples."""
    max_len = max(len(old_children), len(new_children))

    for i in range(max_len):
        path = (*parent_path, i)

        if i >= len(old_children):
            # New node added at end
            changes.append(ASTChange(
                kind="added", path=path,
                old_node=None, new_node=new_children[i],
            ))
        elif i >= len(new_children):
            # Old node removed from end
            changes.append(ASTChange(
                kind="removed", path=path,
                old_node=old_children[i], new_node=None,
            ))
        elif old_children[i] == new_children[i]:
            # Identical subtree — skip (O(1) for frozen nodes)
            continue
        elif type(old_children[i]) is type(new_children[i]):
            # Same type, different content — modified
            changes.append(ASTChange(
                kind="modified", path=path,
                old_node=old_children[i], new_node=new_children[i],
            ))
        else:
            # Different types — remove old, add new
            changes.append(ASTChange(
                kind="removed", path=path,
                old_node=old_children[i], new_node=None,
            ))
            changes.append(ASTChange(
                kind="added", path=path,
                old_node=None, new_node=new_children[i],
            ))
```

---

## 6. Reactive Pipeline Types

### 6.1 ChangeEvent

Produced by the file watcher, consumed by the reactive pipeline.

```python
# purr/content/watcher.py

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    """A file change detected by the watcher.

    Attributes:
        path: Absolute path to the changed file.
        kind: Type of filesystem change.
        category: What kind of file changed (determines pipeline path).
    """

    path: Path
    kind: Literal["created", "modified", "deleted"]
    category: Literal["content", "template", "config", "asset", "route"]
```

### 6.2 BlockUpdate

Produced by the reactive mapper, consumed by the broadcaster.

```python
# purr/reactive/mapper.py

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlockUpdate:
    """A template block that needs re-rendering due to a content change.

    Attributes:
        permalink: Page URL path (e.g., "/docs/getting-started/").
        template_name: Kida template file (e.g., "page.html").
        block_name: Block to re-render (e.g., "content", "sidebar").
        context_paths: The context variables that changed, triggering this update.
    """

    permalink: str
    template_name: str
    block_name: str
    context_paths: frozenset[str]
```

### 6.3 ReactiveMapper

Maps AST changes to affected template blocks using Kida's analysis.

```python
# purr/reactive/mapper.py (continued)

from purr.content.differ import ASTChange


# Mapping from Patitas node types to Bengal template context paths.
# This defines how content structure maps to template variables.
CONTENT_CONTEXT_MAP: dict[str, frozenset[str]] = {
    "Heading":       frozenset({"page.toc", "page.headings", "page.body"}),
    "Paragraph":     frozenset({"page.body"}),
    "FencedCode":    frozenset({"page.body"}),
    "IndentedCode":  frozenset({"page.body"}),
    "List":          frozenset({"page.body"}),
    "ListItem":      frozenset({"page.body"}),
    "BlockQuote":    frozenset({"page.body"}),
    "Table":         frozenset({"page.body"}),
    "ThematicBreak": frozenset({"page.body"}),
    "Directive":     frozenset({"page.body"}),
    "MathBlock":     frozenset({"page.body"}),
    "FootnoteDef":   frozenset({"page.body", "page.footnotes"}),
    "HtmlBlock":     frozenset({"page.body"}),
}

# Catch-all for unknown node types — conservative
FALLBACK_CONTEXT_PATHS = frozenset({"page.body", "page.toc", "page.meta"})


class ReactiveMapper:
    """Maps content AST changes to affected template blocks.

    Uses Kida's block_metadata() to determine which blocks depend on which
    context variables, and CONTENT_CONTEXT_MAP to connect AST node changes
    to context variable changes.
    """

    def map_changes(
        self,
        changes: tuple[ASTChange, ...],
        template_name: str,
        block_metadata: dict[str, frozenset[str]],  # from Kida
        permalink: str,
    ) -> tuple[BlockUpdate, ...]:
        """Map AST changes to block updates.

        Args:
            changes: AST changes from the differ.
            template_name: Kida template for this page.
            block_metadata: Per-block context dependencies from Kida.
            permalink: URL path of the affected page.

        Returns:
            Tuple of BlockUpdate objects for blocks that need re-rendering.
        """
        # 1. Collect all affected context paths from AST changes
        affected_paths: set[str] = set()
        for change in changes:
            node = change.new_node or change.old_node
            if node is not None:
                node_type = type(node).__name__
                paths = CONTENT_CONTEXT_MAP.get(node_type, FALLBACK_CONTEXT_PATHS)
                affected_paths.update(paths)

        # 2. Find blocks whose dependencies intersect affected paths
        updates: list[BlockUpdate] = []
        for block_name, block_deps in block_metadata.items():
            overlap = block_deps & affected_paths
            if overlap:
                updates.append(BlockUpdate(
                    permalink=permalink,
                    template_name=template_name,
                    block_name=block_name,
                    context_paths=frozenset(overlap),
                ))

        return tuple(updates)
```

### 6.4 Broadcaster

Manages SSE connections and pushes fragment updates.

```python
# purr/reactive/broadcaster.py

import threading
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from chirp.realtime.events import SSEEvent


@dataclass(frozen=True, slots=True)
class SSEConnection:
    """A connected SSE client."""

    client_id: str
    permalink: str  # Page being viewed
    queue: object   # asyncio.Queue[SSEEvent] — typed at runtime


class Broadcaster:
    """Manages SSE connections and pushes targeted fragment updates.

    Thread-safe: subscriber map protected by a lock.
    Per-worker: each Pounce worker has its own Broadcaster instance.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[SSEConnection]] = defaultdict(set)
        self._lock = threading.Lock()

    def subscribe(self, permalink: str, conn: SSEConnection) -> None:
        """Register an SSE client for a page."""
        with self._lock:
            self._subscribers[permalink].add(conn)

    def unsubscribe(self, permalink: str, conn: SSEConnection) -> None:
        """Remove an SSE client."""
        with self._lock:
            self._subscribers[permalink].discard(conn)
            if not self._subscribers[permalink]:
                del self._subscribers[permalink]

    def get_subscribers(self, permalink: str) -> frozenset[SSEConnection]:
        """Get all subscribers for a page (snapshot, no lock held on return)."""
        with self._lock:
            return frozenset(self._subscribers.get(permalink, set()))

    async def push(self, permalink: str, event: SSEEvent) -> int:
        """Push an SSE event to all subscribers of a page.

        Returns the number of clients notified.
        """
        subscribers = self.get_subscribers(permalink)
        count = 0
        for conn in subscribers:
            try:
                conn.queue.put_nowait(event)  # type: ignore[attr-defined]
                count += 1
            except Exception:  # noqa: BLE001
                pass  # Client disconnected or queue full
        return count
```

---

## 7. Content Router Types

### 7.1 ContentRoute

Bridges a Bengal page to a Chirp route handler.

```python
# purr/content/router.py

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ContentRoute:
    """A Bengal page registered as a Chirp route.

    Attributes:
        permalink: URL path (e.g., "/docs/getting-started/").
        source_path: Path to the Markdown source file.
        template_name: Kida template to render this page.
        context: Template context from Bengal's content pipeline.
    """

    permalink: str
    source_path: Path
    template_name: str
    context: dict[str, Any]
```

### 7.2 ContentRouter

```python
# purr/content/router.py (continued)

from chirp import App, Request, Response, Template


class ContentRouter:
    """Routes Bengal pages through Chirp's request/response cycle.

    On initialization, iterates all pages from a Bengal Site and registers
    each as a Chirp route. The handler renders the page through Kida via
    Chirp's Template return type.
    """

    def __init__(self) -> None:
        self._routes: list[ContentRoute] = []

    def register_pages(self, site: object, app: App) -> None:
        """Register all Bengal pages as Chirp routes.

        Args:
            site: Bengal Site object with .pages attribute.
            app: Chirp App to register routes on.
        """
        for page in site.pages:  # type: ignore[attr-defined]
            route = ContentRoute(
                permalink=page.permalink,
                source_path=page.source_path,
                template_name=page.template,
                context=page.template_context,
            )
            self._routes.append(route)

            # Create a closure to capture the route
            def make_handler(r: ContentRoute):
                def handler(request: Request) -> Template:
                    return Template(r.template_name, **r.context)
                return handler

            app.route(route.permalink)(make_handler(route))

    def register_sse_endpoint(self, app: App, broadcaster: object) -> None:
        """Register the /__purr/events SSE endpoint.

        Args:
            app: Chirp App to register the endpoint on.
            broadcaster: Broadcaster instance for this worker.
        """
        # Implementation in Phase 2
        ...
```

---

## 8. Application Types

### 8.1 PurrApp

The unified application that wraps Bengal + Chirp.

```python
# purr/app.py

from pathlib import Path

from purr.config import PurrConfig
from purr.content.router import ContentRouter
from purr.reactive.broadcaster import Broadcaster


class PurrApp:
    """Unified Bengal + Chirp application.

    Lifecycle:
    1. Load PurrConfig
    2. Initialize Bengal Site (content discovery + parsing)
    3. Create Chirp App
    4. Register content routes via ContentRouter
    5. Register user routes from routes/ directory
    6. Build dependency graph
    7. Freeze Chirp App
    8. Start serving (mode-dependent)
    """

    def __init__(self, config: PurrConfig) -> None:
        self._config = config
        self._content_router = ContentRouter()
        self._broadcaster = Broadcaster()
        # Bengal Site and Chirp App initialized in load()

    @classmethod
    def from_directory(cls, root: Path, **overrides) -> PurrApp:
        """Create a PurrApp from a site directory.

        Reads purr.yaml if present, applies overrides, and initializes.
        """
        config = PurrConfig(root=root, **overrides)
        return cls(config)
```

---

## 9. CLI Interface

```python
# purr/_cli.py

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="purr",
        description="Content-reactive runtime for the Bengal ecosystem.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # purr dev [root] [--host] [--port]
    dev = subparsers.add_parser("dev", help="Start reactive dev server")
    dev.add_argument("root", nargs="?", default=".")
    dev.add_argument("--host", default="127.0.0.1")
    dev.add_argument("--port", type=int, default=3000)

    # purr build [root] [--output]
    build = subparsers.add_parser("build", help="Export static HTML")
    build.add_argument("root", nargs="?", default=".")
    build.add_argument("--output", default="dist")

    # purr serve [root] [--host] [--port] [--workers]
    serve = subparsers.add_parser("serve", help="Run production server")
    serve.add_argument("root", nargs="?", default=".")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--workers", type=int, default=0)

    return parser
```

---

## 10. Public API Surface

Everything users need is accessible from `purr`:

```python
# purr/__init__.py

_Py_mod_gil = 0  # Free-threading safe

__version__ = "0.1.0-dev"

# Lazy imports via __getattr__:
# purr.dev(root)      → purr.app.dev
# purr.build(root)    → purr.app.build
# purr.serve(root)    → purr.app.serve
# purr.PurrConfig     → purr.config.PurrConfig

__all__ = [
    "PurrConfig",
    "__version__",
    "build",
    "dev",
    "serve",
]
```

**Minimal usage:**

```python
import purr
purr.dev("my-site/")
```

**CLI usage:**

```bash
purr dev my-site/
purr build my-site/ --output dist/
purr serve my-site/ --host 0.0.0.0 --port 8000 --workers 4
```

---

## 11. File Inventory

Summary of all files in the purr package:

```
purr/
├── __init__.py              # Public API (dev, build, serve, PurrConfig)
├── py.typed                 # PEP 561 marker
│
│   # Primitives
├── _types.py                # Type aliases (PurrMode, ContentPath, BlockName, ClientID)
├── _errors.py               # PurrError hierarchy (Config, Content, Reactive, Export)
├── config.py                # PurrConfig frozen dataclass
│
│   # Content Layer
├── content/
│   ├── __init__.py
│   ├── router.py            # ContentRouter — Bengal pages → Chirp routes
│   ├── watcher.py           # ContentWatcher — file changes → ChangeEvent
│   └── differ.py            # ASTDiffer — Patitas AST diffing → ASTChange
│
│   # Reactive Layer
├── reactive/
│   ├── __init__.py
│   ├── graph.py             # DependencyGraph — unified file + block deps
│   ├── mapper.py            # ReactiveMapper — ASTChange → BlockUpdate
│   └── broadcaster.py       # Broadcaster — SSE delivery to clients
│
│   # Export Layer
├── export/
│   ├── __init__.py
│   └── static.py            # StaticExporter — render routes to files
│
│   # Application
├── app.py                   # PurrApp + dev() / build() / serve()
└── _cli.py                  # CLI entry point (argparse)
```

---

## 12. Ecosystem Integration Points

### 12.1 Bengal

```python
# Site model — content discovery
from bengal.core import Site, Page, Section

site.pages        # list[Page] — all content pages
page.permalink    # str — URL path
page.source_path  # Path — Markdown file
page.template     # str — Kida template name
page.template_context  # dict — context for rendering

# Dependency tracking
from bengal.effects import EffectTracer

tracer.outputs_needing_rebuild(changed_paths)  # set[Path]
tracer.invalidated_by(changed_paths)           # set[str] (cache keys)
```

### 12.2 Chirp

```python
# Application and routing
from chirp import App, Request, Response, Template, Fragment, EventStream, SSEEvent

app.route(path)(handler)    # Register a route
Template(name, **ctx)       # Full page render
Fragment(template, block, **ctx)  # Block render
EventStream(generator)      # SSE stream

# Fragment rendering
from chirp.templating.integration import render_fragment
render_fragment(env, fragment)  # → str (HTML)
```

### 12.3 Kida

```python
# Template analysis
template.depends_on()         # frozenset[str] — all context dependencies
template.required_context()   # frozenset[str] — top-level variable names
template.block_metadata()     # dict[str, BlockMetadata] — per-block deps

# BlockMetadata fields
metadata.depends_on           # frozenset[str] — context paths
metadata.is_pure              # "pure" | "impure" | "unknown"
metadata.cache_scope          # "none" | "page" | "site" | "unknown"

# Rendering
template.render(**ctx)              # Full render (StringBuilder)
template.render_block(name, **ctx)  # Block render (StringBuilder)
template.render_stream(**ctx)       # Streaming render (generator)
```

### 12.4 Patitas

```python
# Parsing
from patitas import parse
doc = parse(source, source_file="page.md")  # → Document

# AST nodes — all frozen, hashable, comparable
from patitas.nodes import Document, Heading, Paragraph, FencedCode, ...

doc.children         # tuple[Block, ...]
node.location        # SourceLocation (lineno, col_offset, offset, ...)
node == other_node   # Recursive structural comparison
hash(node)           # Hashable for set/dict use
```

### 12.5 Pounce

```python
# Server
import pounce
pounce.run("purr.app:asgi_app", host="0.0.0.0", port=8000, workers=4)

# Config
from pounce import ServerConfig
config = ServerConfig(host="0.0.0.0", port=8000, workers=4)
```
