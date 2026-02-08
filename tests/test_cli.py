"""Tests for purr._cli — argument parsing and command dispatch."""

from __future__ import annotations

from purr._cli import _build_parser


class TestBuildParser:
    """_build_parser — CLI argument parsing."""

    def test_build_default_args(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["build"])
        assert args.command == "build"
        assert args.root == "."
        assert args.output == "dist"
        assert args.base_url == ""
        assert args.fingerprint is False

    def test_build_with_base_url(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["build", "--base-url", "https://example.com"])
        assert args.base_url == "https://example.com"

    def test_build_with_fingerprint(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["build", "--fingerprint"])
        assert args.fingerprint is True

    def test_build_with_output(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["build", "--output", "public"])
        assert args.output == "public"

    def test_build_with_custom_root(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["build", "my-site/"])
        assert args.root == "my-site/"

    def test_build_all_flags(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "build", "my-site/",
            "--output", "public",
            "--base-url", "https://example.com",
            "--fingerprint",
        ])
        assert args.root == "my-site/"
        assert args.output == "public"
        assert args.base_url == "https://example.com"
        assert args.fingerprint is True

    def test_dev_default_args(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["dev"])
        assert args.command == "dev"
        assert args.root == "."
        assert args.host == "127.0.0.1"
        assert args.port == 3000

    def test_serve_default_args(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["serve"])
        assert args.command == "serve"
        assert args.root == "."
        assert args.host == "0.0.0.0"
        assert args.port == 8000
        assert args.workers == 0

    def test_no_command_returns_none(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.command is None
