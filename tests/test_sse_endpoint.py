"""Tests for the SSE endpoint registration in ContentRouter."""

from __future__ import annotations

from pathlib import Path

import pytest

from purr.content.router import SSE_ENDPOINT, ContentRouter
from purr.reactive.broadcaster import Broadcaster, SSEConnection


class TestSSEEndpointRegistration:
    """Tests for ContentRouter.register_sse_endpoint()."""

    def test_sse_endpoint_constant(self) -> None:
        assert SSE_ENDPOINT == "/__purr/events"

    def test_register_sse_endpoint(self, tmp_path: Path) -> None:
        """SSE endpoint should be registered on the Chirp app."""
        from chirp import App, AppConfig

        from tests.conftest import make_test_site

        site = make_test_site(tmp_path, [])
        app = App(config=AppConfig(template_dir=tmp_path))
        broadcaster = Broadcaster()

        router = ContentRouter(site, app)

        # Should not raise — endpoint is registered on the app
        router.register_sse_endpoint(broadcaster)

        # Verify the route is in the app's pending routes
        route_names = [r.name for r in app._pending_routes if hasattr(r, "name")]
        assert "purr:events" in route_names


class TestBroadcasterIntegration:
    """Integration tests for broadcaster subscribe/push flow."""

    @pytest.mark.asyncio
    async def test_subscribe_push_unsubscribe(self) -> None:
        """Full lifecycle: subscribe -> push -> verify -> unsubscribe."""
        broadcaster = Broadcaster()
        conn = SSEConnection(client_id="test-1", permalink="/docs/")
        broadcaster.subscribe("/docs/", conn)

        assert broadcaster.subscriber_count == 1

        # Push a refresh event
        count = await broadcaster.push_full_refresh("/docs/")
        assert count == 1
        assert not conn.queue.empty()

        event = conn.queue.get_nowait()
        assert event.data == "reload"

        # Unsubscribe
        broadcaster.unsubscribe("/docs/", conn)
        assert broadcaster.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_push_to_correct_page_only(self) -> None:
        """Updates should only go to subscribers of the affected page."""
        broadcaster = Broadcaster()
        conn_a = SSEConnection(client_id="a", permalink="/page-a/")
        conn_b = SSEConnection(client_id="b", permalink="/page-b/")
        broadcaster.subscribe("/page-a/", conn_a)
        broadcaster.subscribe("/page-b/", conn_b)

        # Push only to page-a
        await broadcaster.push_full_refresh("/page-a/")

        assert not conn_a.queue.empty()
        assert conn_b.queue.empty()  # page-b should NOT receive
