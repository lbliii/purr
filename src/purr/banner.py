"""Startup banner — rich, mode-aware status output.

Prints a branded startup banner with timing, status indicators, and the
Bengal cat mascot.  Detects ``NO_COLOR`` / ``TERM`` for safe fallback.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from purr.config import PurrConfig


# ---------------------------------------------------------------------------
# ANSI helpers — respect NO_COLOR (https://no-color.org)
# ---------------------------------------------------------------------------

def _supports_color() -> bool:
    """Return True if the terminal supports ANSI colors."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


_COLOR = _supports_color()

_RESET = "\033[0m" if _COLOR else ""
_BOLD = "\033[1m" if _COLOR else ""
_DIM = "\033[2m" if _COLOR else ""
_CYAN = "\033[36m" if _COLOR else ""
_GREEN = "\033[32m" if _COLOR else ""
_YELLOW = "\033[33m" if _COLOR else ""
_MAGENTA = "\033[35m" if _COLOR else ""
_ORANGE = "\033[38;5;214m" if _COLOR else ""


# ---------------------------------------------------------------------------
# Mode badges
# ---------------------------------------------------------------------------

_MODE_STYLES: dict[str, tuple[str, str]] = {
    "dev": (_GREEN, "dev"),
    "build": (_YELLOW, "build"),
    "serve": (_CYAN, "serve"),
}


def _mode_badge(mode: str) -> str:
    """Return a styled [mode] badge."""
    color, label = _MODE_STYLES.get(mode, (_DIM, mode))
    return f"{color}[{label}]{_RESET}"


# ---------------------------------------------------------------------------
# Clickable URL (OSC 8 hyperlink escape)
# ---------------------------------------------------------------------------

def _clickable_url(url: str) -> str:
    """Wrap *url* in an OSC 8 hyperlink escape if the terminal supports it."""
    if not _COLOR:
        return url
    # OSC 8 ;; url ST  visible text  OSC 8 ;; ST
    return f"\033]8;;{url}\033\\{_BOLD}{_CYAN}{url}{_RESET}\033]8;;\033\\"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def print_banner(
    config: PurrConfig,
    page_count: int,
    mode: str,
    *,
    route_count: int = 0,
    reactive: bool = False,
    load_ms: float = 0.0,
    warnings: list[str] | None = None,
) -> None:
    """Print the Purr startup banner to stderr.

    Args:
        config: Resolved PurrConfig.
        page_count: Number of content pages loaded.
        mode: One of ``"dev"``, ``"build"``, ``"serve"``.
        route_count: Number of dynamic routes discovered.
        reactive: Whether the reactive pipeline is active.
        load_ms: Time spent loading the site in milliseconds.
        warnings: Optional list of warning messages to display.

    """
    from purr import __version__

    # -- header --
    cat = "\u14DA\u1618\u14E2"  # ᓚᘏᗢ
    badge = _mode_badge(mode)
    header = f"  {_ORANGE}{_BOLD}{cat}{_RESET}  Purr {_DIM}v{__version__}{_RESET}  {badge}"

    lines: list[str] = [
        "",
        header,
        f"  {_DIM}{'─' * 43}{_RESET}",
    ]

    # -- status lines --
    pages_label = "page" if page_count == 1 else "pages"
    timing = f" {_DIM}in {load_ms:.0f}ms{_RESET}" if load_ms > 0 else ""
    lines.append(f"  {_DIM}├─{_RESET} {page_count} {pages_label} loaded{timing}")

    if route_count > 0:
        routes_label = "route" if route_count == 1 else "routes"
        lines.append(f"  {_DIM}├─{_RESET} {route_count} dynamic {routes_label}")

    lines.append(f"  {_DIM}├─{_RESET} templates: {_DIM}{config.templates_path}{_RESET}")

    if reactive:
        lines.append(
            f"  {_DIM}├─{_RESET} {_GREEN}live{_RESET} "
            f"— SSE on {_DIM}/__purr/events{_RESET}"
        )

    if mode == "build":
        lines.append(f"  {_DIM}└─{_RESET} output: {_DIM}{config.output_path}{_RESET}")
    elif mode == "serve":
        workers_label = str(config.workers) if config.workers > 0 else "auto"
        lines.append(f"  {_DIM}├─{_RESET} workers: {workers_label}")

    # -- URL (dev / serve) --
    if mode in ("dev", "serve"):
        url = f"http://{config.host}:{config.port}"
        lines.append("")
        lines.append(f"  {_clickable_url(url)}")

    if mode == "dev":
        lines.append("")
        lines.append(f"  {_DIM}Watching for changes...{_RESET}")

    # -- warnings --
    if warnings:
        lines.append("")
        lines.extend(f"  {_YELLOW}!{_RESET} {w}" for w in warnings)

    lines.append("")

    print("\n".join(lines), file=sys.stderr)
