"""Tests for purr.banner — startup banner output."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

from purr.banner import print_banner
from purr.config import PurrConfig


class TestPrintBanner:
    """Tests for the startup banner."""

    def _capture_banner(self, **kwargs: object) -> str:
        """Call print_banner and capture stderr output."""
        buf = io.StringIO()
        with patch.object(sys, "stderr", buf):
            config = PurrConfig(root=Path("/tmp/test-site"))
            print_banner(config, page_count=5, **kwargs)
        return buf.getvalue()

    def test_dev_mode_banner(self) -> None:
        output = self._capture_banner(mode="dev", reactive=True, load_ms=42.5)

        assert "Purr" in output
        assert "5 pages loaded" in output
        assert "42ms" in output
        assert "live" in output or "SSE" in output
        assert "http://127.0.0.1:3000" in output
        assert "Watching for changes" in output

    def test_build_mode_banner(self) -> None:
        output = self._capture_banner(mode="build", load_ms=100.0)

        assert "Purr" in output
        assert "5 pages loaded" in output
        assert "100ms" in output
        assert "output:" in output.lower()

    def test_serve_mode_banner(self) -> None:
        output = self._capture_banner(mode="serve", load_ms=30.0)

        assert "Purr" in output
        assert "5 pages loaded" in output
        assert "workers:" in output.lower()
        assert "http://127.0.0.1:3000" in output

    def test_dynamic_routes_shown(self) -> None:
        output = self._capture_banner(mode="dev", route_count=3)

        assert "3 dynamic routes" in output

    def test_single_page_singular(self) -> None:
        buf = io.StringIO()
        with patch.object(sys, "stderr", buf):
            config = PurrConfig(root=Path("/tmp/test-site"))
            print_banner(config, page_count=1, mode="dev")
        output = buf.getvalue()

        assert "1 page loaded" in output

    def test_warnings_displayed(self) -> None:
        buf = io.StringIO()
        with patch.object(sys, "stderr", buf):
            config = PurrConfig(root=Path("/tmp/test-site"))
            print_banner(
                config, page_count=1, mode="dev",
                warnings=["Missing template: docs.html"],
            )
        output = buf.getvalue()

        assert "Missing template: docs.html" in output

    def test_mascot_present(self) -> None:
        output = self._capture_banner(mode="dev")

        # The banner should contain the Bengal cat mascot ᓚᘏᗢ
        assert "\u14DA\u1618\u14E2" in output

    def test_no_color_respected(self) -> None:
        """When NO_COLOR is set, no ANSI escape codes should appear."""
        buf = io.StringIO()
        with patch.dict("os.environ", {"NO_COLOR": "1"}):
            # Re-import to pick up env change
            import importlib

            import purr.banner
            importlib.reload(purr.banner)
            with patch.object(sys, "stderr", buf):
                config = PurrConfig(root=Path("/tmp/test-site"))
                purr.banner.print_banner(config, page_count=1, mode="dev")
            # Restore original
            importlib.reload(purr.banner)

        output = buf.getvalue()
        assert "\033[" not in output
