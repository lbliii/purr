"""Export layer — static output generation.

Pre-renders the live Purr application as static HTML files,
including both Bengal content pages and dynamic Chirp routes.
"""

from purr.export.static import ExportedFile, ExportResult, StaticExporter

__all__ = ["ExportedFile", "ExportResult", "StaticExporter"]
