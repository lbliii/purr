"""Purr error hierarchy.

All purr-specific errors inherit from PurrError for easy catching.
"""


class PurrError(Exception):
    """Base error for all purr operations."""


class ConfigError(PurrError):
    """Invalid or missing configuration."""


class ContentError(PurrError):
    """Error in content processing (parsing, diffing, routing)."""


class ReactiveError(PurrError):
    """Error in the reactive pipeline (mapping, broadcasting)."""


class ExportError(PurrError):
    """Error during static export."""
