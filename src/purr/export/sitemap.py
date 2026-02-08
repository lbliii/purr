"""Sitemap generation — produce sitemap.xml from exported pages.

Generates a standard sitemap.xml file listing all exported content and
dynamic pages.  Requires ``base_url`` to be configured; skips generation
silently when it is empty.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, SubElement, tostring

if TYPE_CHECKING:
    from purr.export.static import ExportedFile

# XML namespace for sitemaps
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Source types to include in the sitemap
_PAGE_TYPES = frozenset({"content", "dynamic"})


def generate_sitemap(
    pages: tuple[ExportedFile, ...] | list[ExportedFile],
    base_url: str,
) -> str:
    """Generate a sitemap.xml string from exported page records.

    Only includes files with ``source_type`` of ``"content"`` or
    ``"dynamic"``.  Asset, sitemap, and error-page entries are excluded.

    Args:
        pages: Exported file records from the build pipeline.
        base_url: Site base URL (e.g., ``"https://example.com"``).
            Must not end with a trailing slash.

    Returns:
        Complete XML string suitable for writing to ``sitemap.xml``.

    """
    base = base_url.rstrip("/")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urlset = Element("urlset")
    urlset.set("xmlns", _SITEMAP_NS)

    for page in pages:
        if page.source_type not in _PAGE_TYPES:
            continue

        url_el = SubElement(urlset, "url")
        loc = SubElement(url_el, "loc")

        # Normalise the path: ensure it has a trailing slash for clean URLs
        path = page.source_path
        if path != "/" and not path.endswith("/"):
            path = path + "/"
        loc.text = base + path

        lastmod = SubElement(url_el, "lastmod")
        lastmod.text = now

    xml_bytes = tostring(urlset, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes + "\n"


def write_sitemap(
    pages: tuple[ExportedFile, ...] | list[ExportedFile],
    base_url: str,
    output_dir: Path,
) -> ExportedFile | None:
    """Write sitemap.xml to the output directory.

    Returns *None* (with a warning on stderr) if ``base_url`` is empty.

    Args:
        pages: Exported file records from the build pipeline.
        base_url: Site base URL.
        output_dir: Root export output directory.

    Returns:
        An :class:`ExportedFile` record for the sitemap, or *None*.

    """
    from purr.export.static import ExportedFile

    if not base_url:
        print(
            "  Sitemap skipped — set base_url in config to enable",
            file=sys.stderr,
        )
        return None

    t0 = time.perf_counter()
    xml = generate_sitemap(pages, base_url)

    sitemap_path = output_dir / "sitemap.xml"
    data = xml.encode("utf-8")
    sitemap_path.write_bytes(data)
    elapsed = (time.perf_counter() - t0) * 1000

    return ExportedFile(
        source_path="/sitemap.xml",
        output_path=sitemap_path,
        source_type="sitemap",
        size_bytes=len(data),
        duration_ms=elapsed,
    )
