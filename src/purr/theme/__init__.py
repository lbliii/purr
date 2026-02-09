"""Purr theme loader — fallback chain for templates and assets.

User templates (``templates/``) take priority.  When a template is not found
in the user directory, Kida falls through to the bundled default theme.
Same pattern for static assets.

Thread Safety:
    All returned values are read-only path lists.  Safe for free-threading.

"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from purr.config import PurrConfig


def _bundled_theme_path() -> Path:
    """Return the absolute path to the bundled default theme."""
    return Path(__file__).parent / "default"


def get_template_dirs(config: PurrConfig) -> list[Path]:
    """Return template directories in priority order.

    Returns:
        ``[user_templates_dir, bundled_default_templates]``

    Kida's loader searches in order, so user templates take priority.
    The user directory is included even if it does not exist yet (the
    user may create it after startup in dev mode).

    """
    bundled = _bundled_theme_path() / "templates"
    user_dir = config.templates_path

    dirs: list[Path] = []
    # User templates always first (even if dir doesn't exist yet)
    if user_dir != bundled:
        dirs.append(user_dir)
    dirs.append(bundled)
    return dirs


def get_asset_dirs(config: PurrConfig) -> list[Path]:
    """Return static asset directories in priority order.

    Returns:
        ``[user_static_dir, bundled_default_assets]``

    User assets take priority over bundled theme assets.

    """
    bundled = _bundled_theme_path() / "assets"
    user_dir = config.static_path

    dirs: list[Path] = []
    if user_dir != bundled:
        dirs.append(user_dir)
    dirs.append(bundled)
    return dirs
