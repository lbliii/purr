"""Reactive layer — change propagation pipeline.

Connects content changes to browser updates through the dependency graph,
block mapping, and SSE broadcasting.
"""

from purr.reactive.broadcaster import Broadcaster, SSEConnection
from purr.reactive.graph import DependencyGraph
from purr.reactive.mapper import BlockUpdate, ReactiveMapper
from purr.reactive.pipeline import ReactivePipeline

__all__ = [
    "BlockUpdate",
    "Broadcaster",
    "DependencyGraph",
    "ReactivePipeline",
    "ReactiveMapper",
    "SSEConnection",
]
