"""Tests for purr.reactive.error_overlay — dev-mode error overlay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from purr.reactive.error_overlay import (
    error_overlay_middleware,
    format_error_event,
    render_error_page,
)


# ---------------------------------------------------------------------------
# Mock response (matches Chirp's frozen Response pattern)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _MockResponse:
    body: str = ""
    status: int = 200
    content_type: str = "text/html; charset=utf-8"


# ---------------------------------------------------------------------------
# render_error_page
# ---------------------------------------------------------------------------


class TestRenderErrorPage:
    """Tests for rendering exceptions as styled HTML."""

    def test_contains_error_type(self) -> None:
        exc = ValueError("bad value")
        html = render_error_page(exc)

        assert "ValueError" in html
        assert "bad value" in html

    def test_contains_stack_trace(self) -> None:
        try:
            msg = "traceback test"
            raise RuntimeError(msg)
        except RuntimeError as exc:
            html = render_error_page(exc)

        assert "RuntimeError" in html
        assert "traceback test" in html
        assert "Stack trace" in html

    def test_html_escapes_dangerous_content(self) -> None:
        exc = ValueError("<script>alert('xss')</script>")
        html = render_error_page(exc)

        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_contains_inline_css(self) -> None:
        exc = ValueError("test")
        html = render_error_page(exc)

        # Should have inline styles (no external deps)
        assert "<style>" in html
        assert "<!DOCTYPE html>" in html

    def test_source_context_for_real_exception(self) -> None:
        """When we have a real traceback, source context should appear."""
        try:
            msg = "source test"
            raise TypeError(msg)
        except TypeError as exc:
            html = render_error_page(exc)

        # Should contain the source file reference (this test file)
        assert "test_error_overlay.py" in html


# ---------------------------------------------------------------------------
# error_overlay_middleware
# ---------------------------------------------------------------------------


class TestErrorOverlayMiddleware:
    """Tests for the Chirp middleware."""

    @pytest.mark.asyncio
    async def test_passes_through_on_success(self) -> None:
        response = _MockResponse(body="<body>OK</body>")
        mock_next = AsyncMock(return_value=response)

        result = await error_overlay_middleware(object(), mock_next)

        assert result is response

    @pytest.mark.asyncio
    async def test_catches_exception_and_returns_html(self) -> None:
        async def failing_next(_request: object) -> object:
            msg = "template render failed"
            raise RuntimeError(msg)

        result = await error_overlay_middleware(object(), failing_next)

        assert result.status == 500
        assert "text/html" in result.content_type
        assert "RuntimeError" in result.body
        assert "template render failed" in result.body

    @pytest.mark.asyncio
    async def test_error_page_has_reload_button(self) -> None:
        async def failing_next(_request: object) -> object:
            msg = "test error"
            raise ValueError(msg)

        result = await error_overlay_middleware(object(), failing_next)

        assert "Reload" in result.body


# ---------------------------------------------------------------------------
# format_error_event (SSE payload)
# ---------------------------------------------------------------------------


class TestFormatErrorEvent:
    """Tests for the SSE error event formatter."""

    def test_returns_valid_json(self) -> None:
        exc = ValueError("bad input")
        payload = format_error_event(exc)
        data = json.loads(payload)

        assert data["type"] == "ValueError"
        assert data["message"] == "bad input"
        assert "file" in data
        assert "line" in data

    def test_includes_file_and_line(self) -> None:
        try:
            msg = "located error"
            raise TypeError(msg)
        except TypeError as exc:
            payload = format_error_event(exc)
            data = json.loads(payload)

        assert "test_error_overlay.py" in data["file"]
        assert data["line"] > 0
