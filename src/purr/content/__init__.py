"""Content layer — Bengal pages as reactive data.

Handles content routing (Bengal pages -> Chirp routes), file watching,
and AST diffing for the reactive pipeline.
"""

from purr.content.differ import ASTChange, diff_documents
from purr.content.router import ContentRouter
from purr.content.watcher import ChangeEvent, ContentWatcher

__all__ = [
    "ASTChange",
    "ChangeEvent",
    "ContentRouter",
    "ContentWatcher",
    "diff_documents",
]
