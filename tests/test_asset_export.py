"""Tests for purr.export.assets — asset copying and fingerprinting."""

from __future__ import annotations

import json
from pathlib import Path

from purr.export.assets import (
    copy_assets,
    fingerprint_assets,
    rewrite_asset_refs,
    write_manifest,
)


# ---------------------------------------------------------------------------
# Asset copying
# ---------------------------------------------------------------------------


class TestCopyAssets:
    """copy_assets — recursive copy preserving directory structure."""

    def test_copies_files_to_output_static(self, tmp_path: Path) -> None:
        static = tmp_path / "static"
        static.mkdir()
        (static / "style.css").write_text("body { margin: 0; }")
        (static / "app.js").write_text("console.log('hi');")

        output = tmp_path / "dist"
        output.mkdir()

        results = copy_assets(static, output)

        assert len(results) == 2
        assert (output / "static" / "style.css").exists()
        assert (output / "static" / "app.js").exists()
        assert all(r.source_type == "asset" for r in results)

    def test_preserves_directory_structure(self, tmp_path: Path) -> None:
        static = tmp_path / "static"
        (static / "css").mkdir(parents=True)
        (static / "js").mkdir()
        (static / "css" / "main.css").write_text("h1 { color: red; }")
        (static / "js" / "app.js").write_text("// app")

        output = tmp_path / "dist"
        output.mkdir()

        results = copy_assets(static, output)

        assert len(results) == 2
        assert (output / "static" / "css" / "main.css").exists()
        assert (output / "static" / "js" / "app.js").exists()

    def test_skips_hidden_files(self, tmp_path: Path) -> None:
        static = tmp_path / "static"
        static.mkdir()
        (static / "visible.css").write_text("ok")
        (static / ".DS_Store").write_text("hidden")
        (static / "_private.txt").write_text("hidden")

        output = tmp_path / "dist"
        output.mkdir()

        results = copy_assets(static, output)

        assert len(results) == 1
        assert results[0].source_path == "/static/visible.css"

    def test_returns_empty_for_missing_directory(self, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        output.mkdir()

        results = copy_assets(tmp_path / "nonexistent", output)
        assert results == ()

    def test_source_path_format(self, tmp_path: Path) -> None:
        static = tmp_path / "static"
        (static / "img").mkdir(parents=True)
        (static / "img" / "logo.png").write_bytes(b"\x89PNG")

        output = tmp_path / "dist"
        output.mkdir()

        results = copy_assets(static, output)

        assert len(results) == 1
        assert results[0].source_path == "/static/img/logo.png"

    def test_size_bytes_matches_file(self, tmp_path: Path) -> None:
        static = tmp_path / "static"
        static.mkdir()
        content = "body { color: blue; }"
        (static / "style.css").write_text(content)

        output = tmp_path / "dist"
        output.mkdir()

        results = copy_assets(static, output)

        assert results[0].size_bytes == len(content.encode("utf-8"))


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------


class TestFingerprintAssets:
    """fingerprint_assets — content-hash renaming."""

    def test_renames_with_hash(self, tmp_path: Path) -> None:
        static = tmp_path / "static"
        static.mkdir()
        (static / "style.css").write_text("body { margin: 0; }")

        manifest = fingerprint_assets(tmp_path)

        # Original file should not exist
        assert not (static / "style.css").exists()

        # Fingerprinted file should exist
        assert len(manifest) == 1
        original_key = "/static/style.css"
        assert original_key in manifest
        new_path = manifest[original_key]
        assert ".css" in new_path
        # Check 8-char hex hash in filename
        parts = Path(new_path).stem.split(".")
        assert len(parts) == 2
        assert len(parts[1]) == 8

    def test_manifest_accuracy(self, tmp_path: Path) -> None:
        static = tmp_path / "static"
        static.mkdir()
        (static / "a.css").write_text("a")
        (static / "b.js").write_text("b")

        manifest = fingerprint_assets(tmp_path)

        assert len(manifest) == 2
        assert "/static/a.css" in manifest
        assert "/static/b.js" in manifest

        # Verify new files exist
        for new_path in manifest.values():
            full = tmp_path / new_path.lstrip("/")
            assert full.exists()

    def test_returns_empty_for_missing_static_dir(self, tmp_path: Path) -> None:
        manifest = fingerprint_assets(tmp_path)
        assert manifest == {}


# ---------------------------------------------------------------------------
# Asset reference rewriting
# ---------------------------------------------------------------------------


class TestRewriteAssetRefs:
    """rewrite_asset_refs — replace references in HTML files."""

    def test_rewrites_references(self, tmp_path: Path) -> None:
        html = tmp_path / "index.html"
        html.write_text('<link href="/static/style.css">')

        manifest = {"/static/style.css": "/static/style.abc12345.css"}

        rewrite_asset_refs(tmp_path, manifest)

        assert '/static/style.abc12345.css' in html.read_text()
        assert '/static/style.css' not in html.read_text()

    def test_rewrites_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.html").write_text('<link href="/static/s.css">')
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.html").write_text('<script src="/static/s.css">')

        manifest = {"/static/s.css": "/static/s.aabb1122.css"}

        rewrite_asset_refs(tmp_path, manifest)

        assert "/static/s.aabb1122.css" in (tmp_path / "a.html").read_text()
        assert "/static/s.aabb1122.css" in (sub / "b.html").read_text()

    def test_skips_non_html_files(self, tmp_path: Path) -> None:
        (tmp_path / "data.json").write_text('{"css": "/static/style.css"}')

        manifest = {"/static/style.css": "/static/style.xxx.css"}

        rewrite_asset_refs(tmp_path, manifest)

        # JSON file should not be modified
        assert "/static/style.css" in (tmp_path / "data.json").read_text()

    def test_no_op_with_empty_manifest(self, tmp_path: Path) -> None:
        html = tmp_path / "index.html"
        html.write_text("<html>original</html>")

        rewrite_asset_refs(tmp_path, {})

        assert html.read_text() == "<html>original</html>"


# ---------------------------------------------------------------------------
# Manifest writing
# ---------------------------------------------------------------------------


class TestWriteManifest:
    """write_manifest — JSON output."""

    def test_writes_json(self, tmp_path: Path) -> None:
        manifest = {"/static/a.css": "/static/a.1234.css"}
        path = write_manifest(tmp_path, manifest)

        assert path == tmp_path / "manifest.json"
        data = json.loads(path.read_text())
        assert data == manifest

    def test_sorted_keys(self, tmp_path: Path) -> None:
        manifest = {"/static/z.css": "/z", "/static/a.css": "/a"}
        path = write_manifest(tmp_path, manifest)

        text = path.read_text()
        # "a.css" should appear before "z.css"
        assert text.index("/static/a.css") < text.index("/static/z.css")
