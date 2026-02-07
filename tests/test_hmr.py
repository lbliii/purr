"""Tests for purr.reactive.hmr — hot module replacement middleware."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from purr.reactive.hmr import _HMR_SCRIPT, hmr_middleware


# ---------------------------------------------------------------------------
# Minimal response mock (frozen dataclass like Chirp's Response)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _MockResponse:
    body: str = ""
    status: int = 200
    content_type: str = "text/html; charset=utf-8"
    headers: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class _MockSSEResponse:
    """Non-HTML response (no body attribute in the right form)."""

    event_stream: object = None
    content_type: str = "text/event-stream"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_next(response: object) -> AsyncMock:
    """Create a mock 'next' middleware callable."""
    mock_next = AsyncMock(return_value=response)
    return mock_next


def _mock_request() -> object:
    """Create a minimal mock request."""
    return object()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHMRMiddleware:
    """Tests for hmr_middleware."""

    @pytest.mark.asyncio
    async def test_injects_script_before_body_close(self) -> None:
        html = "<html><body><h1>Hello</h1></body></html>"
        response = _MockResponse(body=html)
        result = await hmr_middleware(_mock_request(), _make_next(response))

        assert "data-purr-hmr" in result.body
        assert result.body.index("data-purr-hmr") < result.body.index("</body>")

    @pytest.mark.asyncio
    async def test_injects_before_html_close_if_no_body(self) -> None:
        html = "<html><h1>No body tag</h1></html>"
        response = _MockResponse(body=html)
        result = await hmr_middleware(_mock_request(), _make_next(response))

        assert "data-purr-hmr" in result.body
        assert result.body.index("data-purr-hmr") < result.body.index("</html>")

    @pytest.mark.asyncio
    async def test_appends_if_no_closing_tags(self) -> None:
        html = "<h1>Fragment</h1>"
        response = _MockResponse(body=html)
        result = await hmr_middleware(_mock_request(), _make_next(response))

        assert result.body.endswith("</script>\n")

    @pytest.mark.asyncio
    async def test_skips_non_html_response(self) -> None:
        response = _MockResponse(body='{"key": "value"}', content_type="application/json")
        result = await hmr_middleware(_mock_request(), _make_next(response))

        assert "data-purr-hmr" not in result.body

    @pytest.mark.asyncio
    async def test_skips_sse_response(self) -> None:
        """SSE responses don't have a body to inject into."""
        response = _MockSSEResponse()
        result = await hmr_middleware(_mock_request(), _make_next(response))

        # Should pass through unchanged
        assert result is response

    @pytest.mark.asyncio
    async def test_script_contains_event_source(self) -> None:
        """The injected script should set up an EventSource."""
        assert "EventSource" in _HMR_SCRIPT
        assert "/__purr/events" in _HMR_SCRIPT
        assert "purr:refresh" in _HMR_SCRIPT

    @pytest.mark.asyncio
    async def test_preserves_status_code(self) -> None:
        response = _MockResponse(body="<body></body>", status=200)
        result = await hmr_middleware(_mock_request(), _make_next(response))

        assert result.status == 200
