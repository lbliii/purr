"""Tests for purr.reactive.broadcaster — SSE connection management."""

from __future__ import annotations

import asyncio

import pytest

from purr.reactive.broadcaster import Broadcaster, SSEConnection
from purr.reactive.mapper import BlockUpdate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _conn(client_id: str, permalink: str) -> SSEConnection:
    """Create a test SSEConnection."""
    return SSEConnection(client_id=client_id, permalink=permalink)


def _update(
    permalink: str = "/test/",
    template: str = "page.html",
    block: str = "content",
) -> BlockUpdate:
    return BlockUpdate(
        permalink=permalink,
        template_name=template,
        block_name=block,
        context_paths=frozenset({"page.body"}),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSSEConnection:
    """Verify SSEConnection dataclass."""

    def test_frozen(self) -> None:
        conn = _conn("c1", "/test/")
        with pytest.raises(AttributeError):
            conn.client_id = "other"  # type: ignore[misc]

    def test_has_queue(self) -> None:
        conn = _conn("c1", "/test/")
        assert isinstance(conn.queue, asyncio.Queue)

    def test_equality_by_id_and_permalink(self) -> None:
        """Queue is excluded from comparison (compare=False)."""
        a = _conn("c1", "/test/")
        b = _conn("c1", "/test/")
        assert a == b


class TestBroadcasterSubscriptions:
    """Tests for subscribe/unsubscribe."""

    def test_subscribe_and_get(self) -> None:
        b = Broadcaster()
        conn = _conn("c1", "/page/")
        b.subscribe("/page/", conn)

        subs = b.get_subscribers("/page/")
        assert conn in subs
        assert b.subscriber_count == 1

    def test_multiple_subscribers(self) -> None:
        b = Broadcaster()
        c1 = _conn("c1", "/page/")
        c2 = _conn("c2", "/page/")
        b.subscribe("/page/", c1)
        b.subscribe("/page/", c2)

        assert b.subscriber_count == 2
        assert b.get_subscribers("/page/") == frozenset({c1, c2})

    def test_subscribers_per_page(self) -> None:
        b = Broadcaster()
        c1 = _conn("c1", "/page-a/")
        c2 = _conn("c2", "/page-b/")
        b.subscribe("/page-a/", c1)
        b.subscribe("/page-b/", c2)

        assert b.get_subscribers("/page-a/") == frozenset({c1})
        assert b.get_subscribers("/page-b/") == frozenset({c2})

    def test_unsubscribe(self) -> None:
        b = Broadcaster()
        conn = _conn("c1", "/page/")
        b.subscribe("/page/", conn)
        b.unsubscribe("/page/", conn)

        assert b.subscriber_count == 0
        assert b.get_subscribers("/page/") == frozenset()

    def test_unsubscribe_nonexistent_is_safe(self) -> None:
        b = Broadcaster()
        conn = _conn("c1", "/page/")
        # Should not raise
        b.unsubscribe("/page/", conn)

    def test_get_subscribed_pages(self) -> None:
        b = Broadcaster()
        b.subscribe("/a/", _conn("c1", "/a/"))
        b.subscribe("/b/", _conn("c2", "/b/"))

        pages = b.get_subscribed_pages()
        assert pages == frozenset({"/a/", "/b/"})

    def test_empty_broadcaster(self) -> None:
        b = Broadcaster()
        assert b.subscriber_count == 0
        assert b.get_subscribers("/anything/") == frozenset()
        assert b.get_subscribed_pages() == frozenset()


class TestBroadcasterPush:
    """Tests for push_updates and push_full_refresh."""

    @pytest.mark.asyncio
    async def test_push_updates_to_subscribers(self) -> None:
        b = Broadcaster()
        conn = _conn("c1", "/test/")
        b.subscribe("/test/", conn)

        updates = (_update(permalink="/test/"),)
        count = await b.push_updates(updates, {"page": "context"})

        assert count == 1
        assert not conn.queue.empty()

    @pytest.mark.asyncio
    async def test_push_no_subscribers_returns_zero(self) -> None:
        b = Broadcaster()
        updates = (_update(permalink="/test/"),)
        count = await b.push_updates(updates, {"page": "context"})

        assert count == 0

    @pytest.mark.asyncio
    async def test_push_to_multiple_subscribers(self) -> None:
        b = Broadcaster()
        c1 = _conn("c1", "/test/")
        c2 = _conn("c2", "/test/")
        b.subscribe("/test/", c1)
        b.subscribe("/test/", c2)

        updates = (_update(permalink="/test/"),)
        count = await b.push_updates(updates, {"page": "context"})

        assert count == 2
        assert not c1.queue.empty()
        assert not c2.queue.empty()

    @pytest.mark.asyncio
    async def test_push_multiple_blocks(self) -> None:
        b = Broadcaster()
        conn = _conn("c1", "/test/")
        b.subscribe("/test/", conn)

        updates = (
            _update(permalink="/test/", block="content"),
            _update(permalink="/test/", block="sidebar"),
        )
        count = await b.push_updates(updates, {"page": "context"})

        assert count == 2
        assert conn.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_push_full_refresh(self) -> None:
        b = Broadcaster()
        conn = _conn("c1", "/test/")
        b.subscribe("/test/", conn)

        count = await b.push_full_refresh("/test/")

        assert count == 1
        event = conn.queue.get_nowait()
        assert event.event == "purr:refresh"
        assert event.data == "reload"

    @pytest.mark.asyncio
    async def test_push_full_refresh_no_subscribers(self) -> None:
        b = Broadcaster()
        count = await b.push_full_refresh("/test/")
        assert count == 0


class TestClientGenerator:
    """Tests for the async generator used by EventStream."""

    @pytest.mark.asyncio
    async def test_yields_from_queue(self) -> None:
        b = Broadcaster()
        conn = _conn("c1", "/test/")

        # Put an item before iterating
        conn.queue.put_nowait("test-event")

        gen = b.client_generator(conn)
        item = await gen.__anext__()
        assert item == "test-event"

    @pytest.mark.asyncio
    async def test_cancellation_stops_generator(self) -> None:
        b = Broadcaster()
        conn = _conn("c1", "/test/")

        gen = b.client_generator(conn)

        # Put a sentinel to stop, then cancel — generator returns cleanly
        # The generator catches CancelledError and stops iteration.
        task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.01)
        task.cancel()

        # Generator either raises CancelledError or StopAsyncIteration
        # depending on timing — both indicate correct shutdown.
        with pytest.raises((asyncio.CancelledError, StopAsyncIteration)):
            await task
