"""Load PurrConfig from purr.yaml if present.

Merges file config with CLI kwargs. CLI overrides file.
"""

from __future__ import annotations

from pathlib import Path

from purr.config import PurrConfig


def load_config(root: Path, **overrides: object) -> PurrConfig:
    """Load PurrConfig from root, optionally merging purr.yaml.

    Looks for purr.yaml, purr.yml, or purr.toml in root. If found, loads
    and merges with overrides. Overrides take precedence.
    """
    file_config = _read_purr_config(root)
    merged = {**file_config, **overrides}
    # Normalize output to Path
    if "output" in merged and not isinstance(merged["output"], Path):
        merged["output"] = Path(str(merged["output"]))
    return PurrConfig(root=root, **merged)


def _read_purr_config(root: Path) -> dict[str, object]:
    """Read purr config from yaml/toml if present. Returns empty dict otherwise."""
    for name in ("purr.yaml", "purr.yml"):
        path = root / name
        if path.is_file():
            return _parse_yaml(path)
    toml_path = root / "purr.toml"
    if toml_path.is_file():
        return _parse_toml(toml_path)
    return {}


def _parse_yaml(path: Path) -> dict[str, object]:
    """Parse YAML config. Returns empty dict on error."""
    try:
        import yaml
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return _flatten_purr_section(data)


def _parse_toml(path: Path) -> dict[str, object]:
    """Parse TOML config. Returns empty dict on error."""
    try:
        import tomllib
    except ImportError:
        return {}
    try:
        data = tomllib.loads(path.read_text())
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return _flatten_purr_section(data)


def _flatten_purr_section(data: dict[str, object]) -> dict[str, object]:
    """Extract purr.* keys into top-level config."""
    result: dict[str, object] = {}
    purr = data.get("purr")
    if isinstance(purr, dict):
        for k, v in purr.items():
            result[k] = v
    for k, v in data.items():
        if k != "purr" and k in (
            "auth", "auth_load_user", "session_secret", "gated_metadata_key",
            "host", "port", "output", "base_url", "fingerprint",
            "routes_dir", "content_dir", "templates_dir", "static_dir",
        ):
            result[k] = v
    return result
