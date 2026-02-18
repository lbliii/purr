"""Purr configuration.

PurrConfig is the central configuration object, frozen after creation.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PurrConfig:
    """Configuration for a Purr application.

    Attributes:
        root: Path to the site root directory (contains content/, templates/, etc.).
              Always resolved to an absolute path on construction.
        host: Bind address for dev/serve modes.
        port: Bind port for dev/serve modes.
        output: Output directory for static export.
        workers: Number of Pounce workers (0 = auto-detect).
        routes_dir: Directory containing user-defined Chirp routes.
        content_dir: Directory containing Markdown content.
        templates_dir: Directory containing Kida templates.
        static_dir: Directory containing static assets.
        base_url: Base URL for the site (used for sitemap generation).
        fingerprint: Enable content-hash asset fingerprinting in ``purr build``.
        auth: Enable session + auth middleware (requires chirp[sessions,auth]).
        auth_load_user: Dotted path to async load_user(id) callable, e.g.
            ``auth:load_user`` for routes/auth.py.
        session_secret: Secret key for session signing (required when auth=True).
        gated_metadata_key: Frontmatter key for gated content (default ``gated``).

    """

    root: Path = field(default_factory=Path.cwd)
    host: str = "127.0.0.1"
    port: int = 3000
    output: Path = field(default_factory=lambda: Path("dist"))
    workers: int = 0
    routes_dir: str = "routes"
    content_dir: str = "content"
    templates_dir: str = "templates"
    static_dir: str = "static"
    base_url: str = ""
    fingerprint: bool = False
    auth: bool = False
    auth_load_user: str | None = None
    session_secret: str | None = None
    gated_metadata_key: str = "gated"

    def __post_init__(self) -> None:
        # Resolve root to absolute so that watchfiles (which returns
        # absolute paths) can be compared via Path.relative_to().
        if not self.root.is_absolute():
            object.__setattr__(self, "root", self.root.resolve())

    @property
    def content_path(self) -> Path:
        """Absolute path to content directory."""
        return self.root / self.content_dir

    @property
    def templates_path(self) -> Path:
        """Absolute path to templates directory."""
        return self.root / self.templates_dir

    @property
    def static_path(self) -> Path:
        """Absolute path to static assets directory."""
        return self.root / self.static_dir

    @property
    def routes_path(self) -> Path:
        """Absolute path to user routes directory."""
        return self.root / self.routes_dir

    @property
    def output_path(self) -> Path:
        """Absolute path to output directory."""
        if self.output.is_absolute():
            return self.output
        return self.root / self.output
