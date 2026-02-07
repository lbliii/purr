"""Content layer — Bengal pages as reactive data.

Handles content routing (Bengal pages → Chirp routes), file watching,
and AST diffing for the reactive pipeline.
"""

from purr.content.router import ContentRouter

__all__ = ["ContentRouter"]
