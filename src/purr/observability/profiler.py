"""Pipeline profiler — measures end-to-end reactive pipeline latency.

Provides a lightweight profiler that records per-stage timing for each
reactive update and emits ``PipelineProfile`` events to the ``EventLog``.

Thread Safety:
    The profiler is used from the async pipeline context (single-writer).
    Aggregate queries are protected by the underlying ``EventLog`` lock.

"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from purr.observability.events import PipelineProfile, now_ns

if TYPE_CHECKING:
    from purr.observability.log import EventLog


@dataclass(slots=True)
class _Timer:
    """Accumulates timing for a named pipeline stage."""

    name: str
    _start: float = 0.0
    elapsed_ms: float = 0.0

    def start(self) -> None:
        self._start = time.perf_counter()

    def stop(self) -> None:
        if self._start > 0:
            self.elapsed_ms = (time.perf_counter() - self._start) * 1000
            self._start = 0.0


class PipelineProfiler:
    """Records per-stage timing for a single reactive update.

    Usage::

        profiler = PipelineProfiler(event_log)

        profiler.begin("content/page.md")
        profiler.start("parse")
        # ... parse ...
        profiler.stop("parse")
        profiler.start("diff")
        # ... diff ...
        profiler.stop("diff")
        profiler.finish(blocks_updated=2)

    After ``finish()``, a ``PipelineProfile`` event is appended to the log
    and a one-line summary is printed to stderr.

    """

    __slots__ = ("_log", "_t0", "_timers", "_trigger_path", "_verbose")

    def __init__(self, log: EventLog, *, verbose: bool = True) -> None:
        self._log = log
        self._verbose = verbose
        self._trigger_path = ""
        self._t0 = 0.0
        self._timers: dict[str, _Timer] = {}
        for name in ("parse", "diff", "map", "recompile", "broadcast"):
            self._timers[name] = _Timer(name=name)

    def begin(self, trigger_path: str) -> None:
        """Start profiling a new pipeline update."""
        self._trigger_path = trigger_path
        self._t0 = time.perf_counter()
        for timer in self._timers.values():
            timer.elapsed_ms = 0.0

    def start(self, stage: str) -> None:
        """Start timing a named stage."""
        timer = self._timers.get(stage)
        if timer is not None:
            timer.start()

    def stop(self, stage: str) -> None:
        """Stop timing a named stage."""
        timer = self._timers.get(stage)
        if timer is not None:
            timer.stop()

    def finish(self, *, blocks_updated: int = 0) -> PipelineProfile:
        """Finish profiling and emit the ``PipelineProfile`` event.

        Returns the profile for testing / inspection.

        """
        total_ms = (time.perf_counter() - self._t0) * 1000 if self._t0 > 0 else 0.0

        profile = PipelineProfile(
            trigger_path=self._trigger_path,
            blocks_updated=blocks_updated,
            parse_ms=self._timers["parse"].elapsed_ms,
            diff_ms=self._timers["diff"].elapsed_ms,
            map_ms=self._timers["map"].elapsed_ms,
            recompile_ms=self._timers["recompile"].elapsed_ms,
            broadcast_ms=self._timers["broadcast"].elapsed_ms,
            total_ms=total_ms,
            timestamp_ns=now_ns(),
        )

        self._log.append(profile)

        if self._verbose:
            self._print_summary(profile)

        return profile

    def _print_summary(self, p: PipelineProfile) -> None:
        """Print a one-line timing summary to stderr."""
        # Extract just the filename from the full path
        parts = p.trigger_path.replace("\\", "/").rsplit("/", 1)
        name = parts[-1] if parts else p.trigger_path

        blocks = "block" if p.blocks_updated == 1 else "blocks"
        stages = (
            f"parse: {p.parse_ms:.0f}ms, "
            f"diff: {p.diff_ms:.0f}ms, "
            f"map: {p.map_ms:.0f}ms, "
            f"recompile: {p.recompile_ms:.0f}ms, "
            f"broadcast: {p.broadcast_ms:.0f}ms"
        )
        print(
            f"  [{p.total_ms:.0f}ms] {name} -> "
            f"{p.blocks_updated} {blocks} updated ({stages})",
            file=sys.stderr,
        )


def compute_aggregate_stats(
    log: EventLog,
    *,
    limit: int = 100,
) -> dict:
    """Compute aggregate latency statistics from recent ``PipelineProfile`` events.

    Returns a dict with p50, p95, p99, and per-stage averages.

    """
    profiles = log.query(event_type=PipelineProfile, limit=limit)
    if not profiles:
        return {"count": 0}

    totals = sorted(p.total_ms for p in profiles)
    count = len(totals)

    def percentile(data: list[float], pct: float) -> float:
        idx = int(len(data) * pct / 100)
        return data[min(idx, len(data) - 1)]

    avg_parse = sum(p.parse_ms for p in profiles) / count
    avg_diff = sum(p.diff_ms for p in profiles) / count
    avg_map = sum(p.map_ms for p in profiles) / count
    avg_recompile = sum(p.recompile_ms for p in profiles) / count
    avg_broadcast = sum(p.broadcast_ms for p in profiles) / count

    return {
        "count": count,
        "total_ms": {
            "p50": round(percentile(totals, 50), 1),
            "p95": round(percentile(totals, 95), 1),
            "p99": round(percentile(totals, 99), 1),
            "min": round(totals[0], 1),
            "max": round(totals[-1], 1),
        },
        "avg_by_stage_ms": {
            "parse": round(avg_parse, 1),
            "diff": round(avg_diff, 1),
            "map": round(avg_map, 1),
            "recompile": round(avg_recompile, 1),
            "broadcast": round(avg_broadcast, 1),
        },
    }
