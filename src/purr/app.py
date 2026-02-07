"""Purr application — the unified Bengal + Chirp integration.

PurrApp wraps a Bengal Site and a Chirp App into a single content-reactive application.
The three public functions (dev, build, serve) are the primary entry points.
"""

from __future__ import annotations

from pathlib import Path

from purr.config import PurrConfig


def dev(root: str | Path = ".", **kwargs) -> None:  # noqa: ANN003
    """Start a content-reactive development server.

    Launches a Pounce server with file watching, AST diffing, and SSE broadcasting.
    Content changes propagate to the browser in milliseconds.

    Args:
        root: Path to the site root directory.
        **kwargs: Override PurrConfig fields.

    """
    _config = PurrConfig(root=Path(root), **kwargs)
    raise NotImplementedError(f"purr dev not yet implemented (config: {_config})")


def build(root: str | Path = ".", **kwargs) -> None:  # noqa: ANN003
    """Export the site as static HTML files.

    Renders all content pages and pre-renders dynamic routes with default state.
    Output is deployable to any static hosting (CDN, GitHub Pages, S3, etc.).

    Args:
        root: Path to the site root directory.
        **kwargs: Override PurrConfig fields.

    """
    _config = PurrConfig(root=Path(root), **kwargs)
    raise NotImplementedError(f"purr build not yet implemented (config: {_config})")


def serve(root: str | Path = ".", **kwargs) -> None:  # noqa: ANN003
    """Run the site as a live Pounce server in production.

    Static content is served from memory. Dynamic routes are handled per-request.
    SSE broadcasting is active for connected clients.

    Args:
        root: Path to the site root directory.
        **kwargs: Override PurrConfig fields.

    """
    _config = PurrConfig(root=Path(root), **kwargs)
    raise NotImplementedError(f"purr serve not yet implemented (config: {_config})")
