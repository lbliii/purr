"""Health check endpoint — demonstrates dynamic routes coexisting with content."""

from __future__ import annotations


async def get(request: object) -> str:
    """Return a simple health check response."""
    return '{"status": "ok", "runtime": "purr"}'
