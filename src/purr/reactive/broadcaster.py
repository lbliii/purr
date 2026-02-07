"""SSE broadcaster — pushes fragment updates to connected browsers.

Manages SSE connections per page and coordinates fragment delivery.
When the reactive mapper identifies affected blocks, the broadcaster
re-renders them via Kida and pushes the HTML fragments through Chirp's
EventStream to subscribed clients.
"""

from __future__ import annotations


class Broadcaster:
    """Manages SSE connections and pushes targeted fragment updates.

    Each connected browser subscribes to updates for the page it's viewing.
    When content changes, the broadcaster:

    1. Receives affected blocks from the ReactiveMapper
    2. Re-renders each block via Kida's render_block()
    3. Wraps each as a Chirp Fragment
    4. Pushes to subscribers of the affected page via SSE

    Thread-safe: uses per-page subscriber sets with lock protection.
    """

    # Phase 2: Implementation pending
