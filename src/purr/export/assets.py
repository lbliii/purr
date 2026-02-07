"""Asset handling — copy and optionally fingerprint static assets.

Copies files from the site's ``static/`` directory into the export output,
preserving directory structure.  When fingerprinting is enabled, renames
files with a content-hash suffix and rewrites references in exported HTML.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

from purr.export.static import ExportedFile

# Files/directories skipped during asset copying
_HIDDEN_PREFIXES = (".", "_")


def copy_assets(
    static_path: Path,
    output_dir: Path,
) -> tuple[ExportedFile, ...]:
    """Recursively copy static assets to ``output_dir/static/``.

    Skips hidden files (names starting with ``.`` or ``_``) and
    ``__pycache__`` directories.

    Args:
        static_path: Source directory (e.g., ``site_root/static/``).
        output_dir: Root export output directory.

    Returns:
        Tuple of :class:`ExportedFile` entries, one per copied file.

    """
    if not static_path.is_dir():
        return ()

    dest_root = output_dir / "static"
    results: list[ExportedFile] = []

    for src_file in sorted(static_path.rglob("*")):
        if not src_file.is_file():
            continue

        # Skip hidden files and __pycache__
        if any(part.startswith(tuple(_HIDDEN_PREFIXES)) for part in src_file.parts):
            if "__pycache__" in src_file.parts:
                continue
            # Only skip if the file itself (not an ancestor) is hidden
            if src_file.name.startswith(tuple(_HIDDEN_PREFIXES)):
                continue

        t0 = time.perf_counter()

        relative = src_file.relative_to(static_path)
        dest_file = dest_root / relative
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)

        size = dest_file.stat().st_size
        elapsed = (time.perf_counter() - t0) * 1000

        results.append(ExportedFile(
            source_path=f"/static/{relative}",
            output_path=dest_file,
            source_type="asset",
            size_bytes=size,
            duration_ms=elapsed,
        ))

    return tuple(results)


def fingerprint_assets(output_dir: Path) -> dict[str, str]:
    """Rename static assets with content-hash suffixes.

    For each file in ``output_dir/static/``, computes an 8-character
    hex digest of its contents and renames it:

        ``style.css`` -> ``style.a1b2c3d4.css``

    Args:
        output_dir: Root export output directory.

    Returns:
        Mapping of original paths (``/static/style.css``) to fingerprinted
        paths (``/static/style.a1b2c3d4.css``).

    """
    static_root = output_dir / "static"
    if not static_root.is_dir():
        return {}

    manifest: dict[str, str] = {}

    for filepath in sorted(static_root.rglob("*")):
        if not filepath.is_file():
            continue

        content = filepath.read_bytes()
        digest = hashlib.sha256(content).hexdigest()[:8]

        stem = filepath.stem
        suffix = filepath.suffix
        new_name = f"{stem}.{digest}{suffix}"
        new_path = filepath.with_name(new_name)

        filepath.rename(new_path)

        relative_old = filepath.relative_to(output_dir)
        relative_new = new_path.relative_to(output_dir)
        manifest[f"/{relative_old}"] = f"/{relative_new}"

    return manifest


def rewrite_asset_refs(output_dir: Path, manifest: dict[str, str]) -> None:
    """Rewrite asset references in all exported HTML files.

    Scans ``output_dir`` for ``.html`` files and replaces occurrences of
    original asset paths with their fingerprinted equivalents.

    Args:
        output_dir: Root export output directory.
        manifest: Mapping from ``fingerprint_assets()``.

    """
    if not manifest:
        return

    for html_file in sorted(output_dir.rglob("*.html")):
        content = html_file.read_text(encoding="utf-8")
        modified = False

        for original, fingerprinted in manifest.items():
            if original in content:
                content = content.replace(original, fingerprinted)
                modified = True

        if modified:
            html_file.write_text(content, encoding="utf-8")


def write_manifest(output_dir: Path, manifest: dict[str, str]) -> Path:
    """Write the asset manifest to ``output_dir/manifest.json``.

    Args:
        output_dir: Root export output directory.
        manifest: Mapping from ``fingerprint_assets()``.

    Returns:
        Path to the written manifest file.

    """
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path
