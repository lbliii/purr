"""Shared type definitions for purr."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

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
