"""Shared type definitions for purr."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pathlib import Path

# Mode of operation
type PurrMode = Literal["dev", "build", "serve"]

# Path to a content source file
type ContentPath = Path

# Template block name
type BlockName = str

# SSE client identifier
type ClientID = str

# Route URL path (e.g., "/search", "/api/users")
type RoutePath = str

# Async handler function for a dynamic route
type HandlerFunc = Callable[..., Any]
