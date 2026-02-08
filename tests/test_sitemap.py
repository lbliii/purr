"""Tests for purr.export.sitemap — sitemap.xml generation."""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import fromstring

from purr.export.sitemap import generate_sitemap, write_sitemap
from purr.export.static import ExportedFile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _ef(source_path: str, source_type: str) -> ExportedFile:
    """Shorthand for creating ExportedFile test fixtures."""
    return ExportedFile(
        source_path=source_path,
        output_path=Path(f"/out{source_path}"),
        source_type=source_type,  # type: ignore[arg-type]
        size_bytes=100,
        duration_ms=1.0,
    )


# ---------------------------------------------------------------------------
# generate_sitemap
# ---------------------------------------------------------------------------


class TestGenerateSitemap:
    """generate_sitemap — XML string generation."""

    def test_valid_xml(self) -> None:
        pages = [_ef("/", "content"), _ef("/about/", "content")]
        xml = generate_sitemap(pages, "https://example.com")

        # Should parse without error
        root = fromstring(xml.split("\n", 1)[1])  # skip XML declaration
        assert root.tag == f"{{{_NS}}}urlset"

    def test_correct_urls(self) -> None:
        pages = [
            _ef("/", "content"),
            _ef("/docs/getting-started/", "content"),
        ]
        xml = generate_sitemap(pages, "https://example.com")
        root = fromstring(xml.split("\n", 1)[1])

        locs = [url.find(f"{{{_NS}}}loc").text for url in root.findall(f"{{{_NS}}}url")]

        assert "https://example.com/" in locs
        assert "https://example.com/docs/getting-started/" in locs

    def test_includes_dynamic_routes(self) -> None:
        pages = [
            _ef("/", "content"),
            _ef("/search", "dynamic"),
        ]
        xml = generate_sitemap(pages, "https://example.com")
        root = fromstring(xml.split("\n", 1)[1])

        locs = [url.find(f"{{{_NS}}}loc").text for url in root.findall(f"{{{_NS}}}url")]

        assert "https://example.com/" in locs
        assert "https://example.com/search/" in locs

    def test_excludes_assets_and_sitemap(self) -> None:
        pages = [
            _ef("/", "content"),
            _ef("/static/style.css", "asset"),
            _ef("/sitemap.xml", "sitemap"),
            _ef("/404.html", "error_page"),
        ]
        xml = generate_sitemap(pages, "https://example.com")
        root = fromstring(xml.split("\n", 1)[1])

        urls = root.findall(f"{{{_NS}}}url")
        assert len(urls) == 1
        assert urls[0].find(f"{{{_NS}}}loc").text == "https://example.com/"

    def test_trailing_slash_normalisation(self) -> None:
        pages = [_ef("/search", "dynamic")]
        xml = generate_sitemap(pages, "https://example.com")
        root = fromstring(xml.split("\n", 1)[1])

        loc = root.find(f"{{{_NS}}}url/{{{_NS}}}loc").text
        assert loc == "https://example.com/search/"

    def test_base_url_trailing_slash_stripped(self) -> None:
        pages = [_ef("/", "content")]
        xml = generate_sitemap(pages, "https://example.com/")
        root = fromstring(xml.split("\n", 1)[1])

        loc = root.find(f"{{{_NS}}}url/{{{_NS}}}loc").text
        assert loc == "https://example.com/"

    def test_empty_pages(self) -> None:
        xml = generate_sitemap([], "https://example.com")
        root = fromstring(xml.split("\n", 1)[1])
        assert len(root.findall(f"{{{_NS}}}url")) == 0

    def test_lastmod_present(self) -> None:
        pages = [_ef("/", "content")]
        xml = generate_sitemap(pages, "https://example.com")
        root = fromstring(xml.split("\n", 1)[1])

        lastmod = root.find(f"{{{_NS}}}url/{{{_NS}}}lastmod")
        assert lastmod is not None
        assert lastmod.text is not None
        # Should be YYYY-MM-DD format
        assert len(lastmod.text) == 10


# ---------------------------------------------------------------------------
# write_sitemap
# ---------------------------------------------------------------------------


class TestWriteSitemap:
    """write_sitemap — file writing and skip logic."""

    def test_writes_file(self, tmp_path: Path) -> None:
        pages = [_ef("/", "content")]
        result = write_sitemap(pages, "https://example.com", tmp_path)

        assert result is not None
        assert result.source_type == "sitemap"
        assert (tmp_path / "sitemap.xml").exists()

    def test_returns_none_when_no_base_url(self, tmp_path: Path) -> None:
        pages = [_ef("/", "content")]
        result = write_sitemap(pages, "", tmp_path)

        assert result is None
        assert not (tmp_path / "sitemap.xml").exists()

    def test_file_size_matches(self, tmp_path: Path) -> None:
        pages = [_ef("/", "content"), _ef("/about/", "content")]
        result = write_sitemap(pages, "https://example.com", tmp_path)

        assert result is not None
        actual_size = (tmp_path / "sitemap.xml").stat().st_size
        assert result.size_bytes == actual_size
