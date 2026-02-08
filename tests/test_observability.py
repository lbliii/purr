"""Tests for purr.observability — full-stack event observability."""

import threading
import time

from purr.observability.collector import StackCollector
from purr.observability.events import (
    BlockRecompiled,
    BuildEvent,
    ContentDiffed,
    ContentParsed,
    ReactiveEvent,
    now_ns,
)
from purr.observability.log import EventLog


# ---------------------------------------------------------------------------
# EventLog
# ---------------------------------------------------------------------------


class TestEventLog:
    """Tests for the event log store."""

    def test_append_and_len(self) -> None:
        log = EventLog()
        assert len(log) == 0

        log.append(ContentParsed(
            path="/a.md", incremental=False, blocks_reused=0,
            blocks_reparsed=3, parse_ms=1.0, timestamp_ns=now_ns(),
        ))
        assert len(log) == 1

    def test_max_events_enforced(self) -> None:
        log = EventLog(max_events=5)
        for i in range(10):
            log.append(ContentParsed(
                path=f"/{i}.md", incremental=False, blocks_reused=0,
                blocks_reparsed=1, parse_ms=0.1, timestamp_ns=now_ns(),
            ))
        assert len(log) == 5

    def test_recent(self) -> None:
        log = EventLog()
        for i in range(5):
            log.append(ContentParsed(
                path=f"/{i}.md", incremental=False, blocks_reused=0,
                blocks_reparsed=1, parse_ms=0.1, timestamp_ns=now_ns(),
            ))
        recent = log.recent(3)
        assert len(recent) == 3
        assert recent[-1].path == "/4.md"

    def test_query_by_type(self) -> None:
        log = EventLog()
        log.append(ContentParsed(
            path="/a.md", incremental=False, blocks_reused=0,
            blocks_reparsed=1, parse_ms=0.1, timestamp_ns=now_ns(),
        ))
        log.append(BuildEvent(
            kind="render", source="/a.md", target="/a.html",
            duration_ms=5.0, timestamp_ns=now_ns(),
        ))
        log.append(ContentParsed(
            path="/b.md", incremental=True, blocks_reused=2,
            blocks_reparsed=1, parse_ms=0.05, timestamp_ns=now_ns(),
        ))

        results = log.query(event_type=ContentParsed)
        assert len(results) == 2
        assert all(isinstance(r, ContentParsed) for r in results)

    def test_query_by_path(self) -> None:
        log = EventLog()
        log.append(ContentParsed(
            path="/docs/api.md", incremental=False, blocks_reused=0,
            blocks_reparsed=3, parse_ms=1.0, timestamp_ns=now_ns(),
        ))
        log.append(ContentParsed(
            path="/blog/post.md", incremental=False, blocks_reused=0,
            blocks_reparsed=2, parse_ms=0.5, timestamp_ns=now_ns(),
        ))

        results = log.query(path="docs")
        assert len(results) == 1
        assert results[0].path == "/docs/api.md"

    def test_clear(self) -> None:
        log = EventLog()
        for i in range(3):
            log.append(ContentParsed(
                path=f"/{i}.md", incremental=False, blocks_reused=0,
                blocks_reparsed=1, parse_ms=0.1, timestamp_ns=now_ns(),
            ))
        cleared = log.clear()
        assert cleared == 3
        assert len(log) == 0

    def test_stats(self) -> None:
        log = EventLog()
        log.append(ContentParsed(
            path="/a.md", incremental=False, blocks_reused=0,
            blocks_reparsed=1, parse_ms=0.1, timestamp_ns=now_ns(),
        ))
        log.append(BuildEvent(
            kind="render", source="/a.md", target="/a.html",
            duration_ms=5.0, timestamp_ns=now_ns(),
        ))

        stats = log.stats()
        assert stats["total"] == 2
        assert stats["by_type"]["ContentParsed"] == 1
        assert stats["by_type"]["BuildEvent"] == 1

    def test_thread_safety(self) -> None:
        """Concurrent appends should not lose events."""
        log = EventLog(max_events=50_000)
        errors: list[Exception] = []

        def worker(start: int) -> None:
            try:
                for i in range(1000):
                    log.append(ContentParsed(
                        path=f"/{start}_{i}.md", incremental=False,
                        blocks_reused=0, blocks_reparsed=1,
                        parse_ms=0.01, timestamp_ns=now_ns(),
                    ))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(log) == 10_000


# ---------------------------------------------------------------------------
# StackCollector
# ---------------------------------------------------------------------------


class TestStackCollector:
    """Tests for the unified stack collector."""

    def test_record_pounce_event(self) -> None:
        """Pounce lifecycle events are stored via record()."""
        collector = StackCollector()

        # Simulate a Pounce event (use a ContentParsed as stand-in
        # since Pounce may not be importable)
        event = ContentParsed(
            path="/test.md", incremental=False, blocks_reused=0,
            blocks_reparsed=1, parse_ms=0.1, timestamp_ns=now_ns(),
        )
        collector.record(event)

        assert len(collector.log) == 1

    def test_record_parse(self) -> None:
        collector = StackCollector()
        collector.record_parse("/docs/api.md", incremental=True, blocks_reused=5, blocks_reparsed=1, parse_ms=0.3)

        events = collector.log.query(event_type=ContentParsed)
        assert len(events) == 1
        assert events[0].incremental is True
        assert events[0].blocks_reused == 5

    def test_record_diff(self) -> None:
        collector = StackCollector()
        collector.record_diff("/a.md", changes_count=3, added=1, removed=1, modified=1)

        events = collector.log.query(event_type=ContentDiffed)
        assert len(events) == 1
        assert events[0].changes_count == 3

    def test_record_build(self) -> None:
        collector = StackCollector()
        collector.record_build("render", "/a.md", "/a.html", duration_ms=12.5)

        events = collector.log.query(event_type=BuildEvent)
        assert len(events) == 1
        assert events[0].kind == "render"
        assert events[0].duration_ms == 12.5

    def test_record_reactive_update(self) -> None:
        collector = StackCollector()
        collector.record_reactive_update(
            "/docs/api/",
            blocks_updated=2,
            blocks_recompiled=1,
            clients_notified=3,
            trigger_path="/docs/api.md",
            duration_ms=15.0,
        )

        events = collector.log.query(event_type=ReactiveEvent)
        assert len(events) == 1
        assert events[0].blocks_updated == 2
        assert events[0].clients_notified == 3

    def test_record_block_recompile(self) -> None:
        collector = StackCollector()
        collector.record_block_recompile("page.html", "content", reason="content_change")

        events = collector.log.query(event_type=BlockRecompiled)
        assert len(events) == 1
        assert events[0].template_name == "page.html"
        assert events[0].block_name == "content"

    def test_collector_with_custom_log(self) -> None:
        log = EventLog(max_events=50)
        collector = StackCollector(log)

        collector.record_parse("/test.md", parse_ms=1.0)
        assert len(log) == 1
        assert collector.log is log


# ---------------------------------------------------------------------------
# Event dataclasses
# ---------------------------------------------------------------------------


class TestEventDataclasses:
    """Tests for event immutability and structure."""

    def test_content_parsed_frozen(self) -> None:
        event = ContentParsed(
            path="/a.md", incremental=True, blocks_reused=3,
            blocks_reparsed=1, parse_ms=0.5, timestamp_ns=now_ns(),
        )
        assert event.incremental is True
        try:
            event.path = "/b.md"  # type: ignore[misc]
            raise AssertionError("Should have raised")
        except AttributeError:
            pass  # Expected — frozen

    def test_reactive_event_fields(self) -> None:
        event = ReactiveEvent(
            permalink="/docs/",
            blocks_updated=2,
            blocks_recompiled=1,
            clients_notified=5,
            trigger_path="/docs/index.md",
            duration_ms=10.0,
            timestamp_ns=now_ns(),
        )
        assert event.permalink == "/docs/"
        assert event.blocks_recompiled == 1

    def test_now_ns_monotonic(self) -> None:
        t1 = now_ns()
        t2 = now_ns()
        assert t2 >= t1
