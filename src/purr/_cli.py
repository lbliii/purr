"""Purr CLI — purr dev / purr build / purr serve.

Entry point for the ``purr`` command-line interface.
"""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the purr CLI."""
    parser = argparse.ArgumentParser(
        prog="purr",
        description="Content-reactive runtime for the Bengal ecosystem.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # purr dev
    dev_parser = subparsers.add_parser(
        "dev",
        help="Start content-reactive development server",
    )
    dev_parser.add_argument("root", nargs="?", default=".", help="Site root directory")
    dev_parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    dev_parser.add_argument("--port", type=int, default=3000, help="Bind port")

    # purr build
    build_parser = subparsers.add_parser(
        "build",
        help="Export site as static HTML files",
    )
    build_parser.add_argument("root", nargs="?", default=".", help="Site root directory")
    build_parser.add_argument("--output", default="dist", help="Output directory")
    build_parser.add_argument(
        "--base-url", default="", help="Base URL for sitemap generation",
    )
    build_parser.add_argument(
        "--fingerprint", action="store_true", help="Enable asset fingerprinting",
    )

    # purr serve
    serve_parser = subparsers.add_parser(
        "serve",
        help="Run live production server",
    )
    serve_parser.add_argument("root", nargs="?", default=".", help="Site root directory")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port")
    serve_parser.add_argument("--workers", type=int, default=0, help="Worker count (0=auto)")

    return parser


def _get_version() -> str:
    """Get the package version."""
    from purr import __version__

    return __version__


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    from purr.app import build, dev, serve

    if args.command == "dev":
        dev(root=args.root, host=args.host, port=args.port)
    elif args.command == "build":
        build(
            root=args.root,
            output=args.output,
            base_url=args.base_url,
            fingerprint=args.fingerprint,
        )
    elif args.command == "serve":
        serve(root=args.root, host=args.host, port=args.port, workers=args.workers)


if __name__ == "__main__":
    main()
