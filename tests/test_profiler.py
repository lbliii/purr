"""Tests for purr.observability.profiler — pipeline performance profiling."""

from __future__ import annotations

import io
import sys
from unittest.mock import patch

from purr.observability.events import PipelineProfile
from purr.observability.log import EventLog
from purr.observability.profiler import (
    PipelineProfiler,
    compute_aggregate_stats,
)


class TestPipelineProfiler:
    """Tests for the pipeline profiler."""

    def test_begin_and_finish_emits_event(self) -> None:
        log = EventLog()
        profiler = PipelineProfiler(log, verbose=False)

        profiler.begin("/content/page.md")
        profiler.start("parse")
        profiler.stop("parse")
        profiler.start("diff")
        profiler.stop("diff")
        profile = profiler.finish(blocks_updated=2)

        assert isinstance(profile, PipelineProfile)
        assert profile.trigger_path == "/content/page.md"
        assert profile.blocks_updated == 2
        assert profile.total_ms > 0
        assert len(log) == 1

    def test_per_stage_timing(self) -> None:
        log = EventLog()
        profiler = PipelineProfiler(log, verbose=False)

        profiler.begin("/test.md")
        profiler.start("parse")
        # Simulate some work
        profiler.stop("parse")
        profiler.start("diff")
        profiler.stop("diff")
        profiler.start("map")
        profiler.stop("map")
        profiler.start("recompile")
        profiler.stop("recompile")
        profiler.start("broadcast")
        profiler.stop("broadcast")
        profile = profiler.finish(blocks_updated=1)

        # All stage timings should be non-negative
        assert profile.parse_ms >= 0
        assert profile.diff_ms >= 0
        assert profile.map_ms >= 0
        assert profile.recompile_ms >= 0
        assert profile.broadcast_ms >= 0

    def test_verbose_prints_summary(self) -> None:
        log = EventLog()
        profiler = PipelineProfiler(log, verbose=True)

        buf = io.StringIO()
        with patch.object(sys, "stderr", buf):
            profiler.begin("/content/page.md")
            profiler.start("parse")
            profiler.stop("parse")
            profiler.finish(blocks_updated=3)

        output = buf.getvalue()
        assert "page.md" in output
        assert "3 blocks" in output
        assert "parse:" in output

    def test_silent_when_not_verbose(self) -> None:
        log = EventLog()
        profiler = PipelineProfiler(log, verbose=False)

        buf = io.StringIO()
        with patch.object(sys, "stderr", buf):
            profiler.begin("/test.md")
            profiler.finish(blocks_updated=1)

        assert buf.getvalue() == ""

    def test_multiple_profiles(self) -> None:
        log = EventLog()
        profiler = PipelineProfiler(log, verbose=False)

        for i in range(5):
            profiler.begin(f"/page{i}.md")
            profiler.start("parse")
            profiler.stop("parse")
            profiler.finish(blocks_updated=i)

        assert len(log) == 5
        profiles = log.query(event_type=PipelineProfile)
        assert len(profiles) == 5


class TestAggregateStats:
    """Tests for compute_aggregate_stats."""

    def test_empty_log(self) -> None:
        log = EventLog()
        stats = compute_aggregate_stats(log)

        assert stats["count"] == 0

    def test_basic_stats(self) -> None:
        log = EventLog()
        profiler = PipelineProfiler(log, verbose=False)

        for i in range(10):
            profiler.begin(f"/page{i}.md")
            profiler.start("parse")
            profiler.stop("parse")
            profiler.finish(blocks_updated=1)

        stats = compute_aggregate_stats(log)

        assert stats["count"] == 10
        assert "p50" in stats["total_ms"]
        assert "p95" in stats["total_ms"]
        assert "p99" in stats["total_ms"]
        assert "parse" in stats["avg_by_stage_ms"]
        assert "broadcast" in stats["avg_by_stage_ms"]

    def test_percentiles_are_ordered(self) -> None:
        log = EventLog()
        profiler = PipelineProfiler(log, verbose=False)

        for i in range(20):
            profiler.begin(f"/page{i}.md")
            profiler.finish(blocks_updated=1)

        stats = compute_aggregate_stats(log)

        assert stats["total_ms"]["p50"] <= stats["total_ms"]["p95"]
        assert stats["total_ms"]["p95"] <= stats["total_ms"]["p99"]
        assert stats["total_ms"]["min"] <= stats["total_ms"]["max"]


class TestPipelineProfileEvent:
    """Tests for the PipelineProfile event dataclass."""

    def test_frozen(self) -> None:
        from purr.observability.events import now_ns

        profile = PipelineProfile(
            trigger_path="/a.md",
            blocks_updated=2,
            parse_ms=1.0,
            diff_ms=0.5,
            map_ms=0.2,
            recompile_ms=3.0,
            broadcast_ms=1.5,
            total_ms=6.2,
            timestamp_ns=now_ns(),
        )
        assert profile.blocks_updated == 2
        try:
            profile.blocks_updated = 5  # type: ignore[misc]
            raise AssertionError("Should have raised")
        except AttributeError:
            pass  # Expected — frozen

    def test_in_stack_event_union(self) -> None:
        """PipelineProfile should be part of the StackEvent union."""
        from purr.observability.events import now_ns

        profile = PipelineProfile(
            trigger_path="/a.md",
            blocks_updated=1,
            parse_ms=0.0,
            diff_ms=0.0,
            map_ms=0.0,
            recompile_ms=0.0,
            broadcast_ms=0.0,
            total_ms=0.0,
            timestamp_ns=now_ns(),
        )
        # Should be appendable to EventLog without error
        log = EventLog()
        log.append(profile)
        assert len(log) == 1
