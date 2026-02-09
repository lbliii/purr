"""Content router — serves Bengal pages as Chirp routes.

Maps Bengal's content model (pages, sections, assets) to Chirp's routing system,
creating a unified URL space where static content and dynamic routes coexist.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bengal.core.page import Page
    from bengal.core.site import Site
    from chirp import App, Request

    from purr.observability.collector import StackCollector
    from purr.reactive.broadcaster import Broadcaster


_DEFAULT_TEMPLATE = "page.html"
_INDEX_TEMPLATE = "index.html"

# SSE endpoint path for reactive updates
SSE_ENDPOINT = "/__purr/events"
STATS_ENDPOINT = "/__purr/stats"


def _resolve_template_name(page: Page) -> str:
    """Determine which template to use for a page.

    Resolution order:
        1. Explicit ``template`` key in page frontmatter/metadata.
        2. ``index.html`` for section index pages (``_index.md``).
        3. ``page.html`` as the default fallback.

    This is a simplified version of Bengal's full template resolution chain.
    Bengal's renderer considers content-type strategies, section-based detection,
    and cascade inheritance.  Phase 1 keeps it simple: explicit override or default.

    """
    # 1. Explicit template in frontmatter
    explicit = page.metadata.get("template") if hasattr(page, "metadata") else None
    if explicit:
        return str(explicit)

    # 2. Index pages use index.html
    if hasattr(page, "source_path") and page.source_path and page.source_path.name == "_index.md":
        return _INDEX_TEMPLATE

    # 3. Default
    return _DEFAULT_TEMPLATE


class ContentRouter:
    """Routes Bengal pages through Chirp's request/response cycle.

    Discovers Bengal pages at startup and registers each as a Chirp route.
    Pages are rendered through Kida templates via Chirp's template integration.

    Args:
        site: Bengal Site containing discovered pages and sections.
        app: Chirp App to register routes on (must not yet be frozen).

    """

    def __init__(self, site: Site, app: App) -> None:
        self._site = site
        self._app = app
        self._page_count = 0

    @property
    def page_count(self) -> int:
        """Number of content pages registered as routes."""
        return self._page_count

    def register_pages(self) -> None:
        """Register each Bengal page as a Chirp route at its permalink.

        Iterates ``site.pages`` and creates a GET route for each page.
        The route handler builds a Bengal template context and returns a
        Chirp ``Template`` response that Kida renders.

        Must be called before the Chirp app is frozen (before first request).

        """
        for page in self._site.pages:
            permalink = self._get_permalink(page)
            if not permalink:
                continue

            template_name = _resolve_template_name(page)
            handler = self._make_page_handler(page, template_name)

            # Register as a Chirp route — use the decorator as a function call
            self._app.route(permalink, name=f"page:{permalink}")(handler)
            self._page_count += 1

    def _get_permalink(self, page: Page) -> str | None:
        """Extract the URL path for a page.

        Tries ``href``, ``_path``, then falls back to building from source path.
        Returns *None* if no usable path can be determined.

        """
        # Bengal pages expose href (template-ready URL with baseurl)
        if hasattr(page, "href") and page.href:
            return str(page.href)

        # Fallback: internal site-relative path
        if hasattr(page, "_path") and page._path:
            path = str(page._path)
            if not path.startswith("/"):
                path = "/" + path
            return path

        return None

    def register_sse_endpoint(self, broadcaster: Broadcaster) -> None:
        """Register the ``/__purr/events`` SSE endpoint.

        Clients connect with a ``page`` query parameter to subscribe to
        reactive updates for a specific page. The route returns a Chirp
        ``EventStream`` that pushes Fragment and SSEEvent objects from the
        broadcaster's per-connection queue.

        Args:
            broadcaster: Broadcaster instance managing SSE subscriptions.

        """
        from chirp import EventStream

        from purr.reactive.broadcaster import SSEConnection

        async def sse_handler(request: Request) -> Any:
            # Extract the page permalink from query params
            permalink = request.query.get("page", "/")
            client_id = str(uuid.uuid4())

            conn = SSEConnection(client_id=client_id, permalink=permalink)
            broadcaster.subscribe(permalink, conn)

            async def generate():  # type: ignore[return]
                try:
                    async for event in broadcaster.client_generator(conn):
                        yield event
                finally:
                    broadcaster.unsubscribe(permalink, conn)

            return EventStream(generate())

        sse_handler.__name__ = "purr_sse"
        sse_handler.__qualname__ = "ContentRouter.purr_sse"

        self._app.route(SSE_ENDPOINT, name="purr:events")(sse_handler)

    def register_stats_endpoint(self, collector: StackCollector) -> None:
        """Register the ``/__purr/stats`` JSON endpoint.

        Returns aggregate pipeline profiling stats and event log summary.

        Args:
            collector: StackCollector for accessing the event log.

        """
        import json

        async def stats_handler(request: Request) -> Any:
            from chirp.http.response import Response

            from purr.observability.profiler import compute_aggregate_stats

            stats = compute_aggregate_stats(collector.log)
            log_stats = collector.log.stats()

            payload = json.dumps(
                {"pipeline": stats, "event_log": log_stats},
                indent=2,
            )

            return Response(
                body=payload,
                status=200,
                content_type="application/json",
            )

        stats_handler.__name__ = "purr_stats"
        stats_handler.__qualname__ = "ContentRouter.purr_stats"

        self._app.route(STATS_ENDPOINT, name="purr:stats")(stats_handler)

    def _make_page_handler(self, page: Page, template_name: str) -> Any:
        """Create a Chirp route handler that renders a Bengal page.

        The handler captures ``page``, ``site``, and ``template_name`` via closure.
        On each request it builds the full Bengal template context and returns a
        Chirp ``Template`` object for Kida to render.

        """
        site = self._site

        async def page_handler(request: Request) -> Any:
            from bengal.rendering.context import build_page_context
            from chirp import Template

            content = page.html_content or ""
            context = build_page_context(page, site, content=content, lazy=True)
            return Template(template_name, **context)

        # Give the handler a useful name for debugging
        page_handler.__name__ = f"page_{self._page_count}"
        page_handler.__qualname__ = f"ContentRouter.page_{self._page_count}"

        return page_handler
