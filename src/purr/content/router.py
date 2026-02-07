"""Content router — serves Bengal pages as Chirp routes.

Maps Bengal's content model (pages, sections, assets) to Chirp's routing system,
creating a unified URL space where static content and dynamic routes coexist.
"""

from __future__ import annotations


class ContentRouter:
    """Routes Bengal pages through Chirp's request/response cycle.

    Discovers Bengal pages at startup and registers each as a Chirp route.
    Pages are rendered through Kida templates via Chirp's template integration.

    The router also mounts the SSE endpoint (``/__purr/events``) for the
    reactive pipeline in dev/serve modes.
    """

    # Phase 1: Implementation pending
