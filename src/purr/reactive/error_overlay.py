"""Dev-mode error overlay — renders exceptions as styled HTML.

Provides two mechanisms:
1. ``error_overlay_middleware`` — Chirp middleware that catches render errors
   and returns a styled error page in the browser (instead of a bare 500).
2. ``format_error_event`` — Formats an exception as an SSE-safe JSON payload
   for broadcasting via the ``purr:error`` event.

Only active when ``debug=True`` (dev mode).
"""

from __future__ import annotations

import html
import json
import linecache
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp.http.request import Request
    from chirp.http.response import Response, SSEResponse, StreamingResponse
    from chirp.middleware.protocol import Next

    type AnyResponse = Response | StreamingResponse | SSEResponse


# ---------------------------------------------------------------------------
# Error page template (inline CSS — works even if static files are broken)
# ---------------------------------------------------------------------------

_ERROR_PAGE = """\
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Purr — Error</title>
<style>
*,*::before,*::after{{box-sizing:border-box}}
body{{margin:0;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
  background:#1a1a1a;color:#e0e0e0;line-height:1.6}}
.overlay{{max-width:860px;margin:2rem auto;padding:0 1.5rem}}
.error-header{{background:#2d1010;border:1px solid #e74c3c;border-radius:8px;
  padding:1.25rem 1.5rem;margin-bottom:1.5rem}}
.error-header h1{{margin:0;font-size:1rem;color:#e74c3c;font-weight:600}}
.error-header .message{{margin:0.5rem 0 0;font-size:0.95rem;color:#f0a0a0;
  word-break:break-word}}
.source{{background:#1e1e1e;border:1px solid #3a3a3a;border-radius:8px;
  padding:1rem 0;margin-bottom:1.5rem;overflow-x:auto}}
.source .file{{padding:0 1.25rem;margin-bottom:0.75rem;font-size:0.8rem;color:#9e9e9e}}
.source pre{{margin:0;padding:0;font-size:0.85rem}}
.source .line{{display:block;padding:0 1.25rem;white-space:pre}}
.source .line.error-line{{background:#3a1515;border-left:3px solid #e74c3c}}
.source .line .num{{display:inline-block;width:3.5rem;color:#757575;
  text-align:right;padding-right:1rem;user-select:none}}
details{{margin-bottom:1.5rem}}
summary{{cursor:pointer;color:#9e9e9e;font-size:0.85rem;
  padding:0.5rem 0;user-select:none}}
summary:hover{{color:#e0e0e0}}
.trace{{background:#1e1e1e;border:1px solid #3a3a3a;border-radius:8px;
  padding:1rem 1.25rem;font-size:0.8rem;overflow-x:auto;white-space:pre;
  color:#9e9e9e;max-height:400px;overflow-y:auto}}
.actions{{display:flex;gap:0.75rem}}
.actions button{{padding:0.5rem 1.25rem;border-radius:6px;border:1px solid #3a3a3a;
  background:#2d2d2d;color:#e0e0e0;cursor:pointer;font-size:0.85rem;
  font-family:inherit}}
.actions button:hover{{background:#3a3a3a}}
.actions .primary{{background:#e74c3c;border-color:#e74c3c;color:#fff}}
.actions .primary:hover{{background:#c0392b}}
</style>
</head>
<body>
<div class="overlay">
  <div class="error-header">
    <h1>{error_type}</h1>
    <p class="message">{error_message}</p>
  </div>
  {source_section}
  <details>
    <summary>Stack trace</summary>
    <div class="trace">{stack_trace}</div>
  </details>
  <div class="actions">
    <button class="primary" onclick="location.reload()">Reload</button>
  </div>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Source context extraction
# ---------------------------------------------------------------------------

def _extract_source_context(
    filename: str,
    lineno: int,
    context: int = 5,
) -> str:
    """Read source lines around the error and render as HTML."""
    if not filename or lineno <= 0:
        return ""

    start = max(1, lineno - context)
    end = lineno + context

    lines_html: list[str] = []
    for i in range(start, end + 1):
        line = linecache.getline(filename, i)
        if not line and i > lineno:
            break
        escaped = html.escape(line.rstrip())
        cls = ' class="line error-line"' if i == lineno else ' class="line"'
        lines_html.append(
            f'<span{cls}><span class="num">{i}</span>{escaped}</span>'
        )

    if not lines_html:
        return ""

    escaped_file = html.escape(filename)
    return (
        f'<div class="source">'
        f'<div class="file">{escaped_file}:{lineno}</div>'
        f'<pre>{"".join(lines_html)}</pre>'
        f'</div>'
    )


def _extract_error_location(exc: BaseException) -> tuple[str, int]:
    """Extract the most relevant filename and line number from an exception."""
    tb = exc.__traceback__
    if tb is None:
        return "", 0

    # Walk to the innermost frame
    while tb.tb_next is not None:
        tb = tb.tb_next

    return tb.tb_frame.f_code.co_filename, tb.tb_lineno


# ---------------------------------------------------------------------------
# HTML error page builder
# ---------------------------------------------------------------------------

def render_error_page(exc: BaseException) -> str:
    """Render a full HTML error page for the given exception."""
    error_type = html.escape(type(exc).__qualname__)
    error_message = html.escape(str(exc))
    stack_trace = html.escape(
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    )

    filename, lineno = _extract_error_location(exc)
    source_section = _extract_source_context(filename, lineno)

    return _ERROR_PAGE.format(
        error_type=error_type,
        error_message=error_message,
        source_section=source_section,
        stack_trace=stack_trace,
    )


# ---------------------------------------------------------------------------
# Chirp middleware
# ---------------------------------------------------------------------------

async def error_overlay_middleware(request: Request, next: Next) -> AnyResponse:
    """Chirp middleware that catches exceptions and renders a styled error page.

    Only wraps the request handling — if the inner handler raises, we catch
    it and return an HTML error overlay instead of letting the 500 propagate.

    """
    try:
        return await next(request)
    except Exception as exc:
        from chirp.http.response import Response

        error_html = render_error_page(exc)
        return Response(
            body=error_html,
            status=500,
            content_type="text/html; charset=utf-8",
        )


# ---------------------------------------------------------------------------
# SSE error event helper
# ---------------------------------------------------------------------------

def format_error_event(exc: BaseException) -> str:
    """Format an exception as a JSON payload for SSE ``purr:error`` events.

    The HMR script in the browser receives this and renders an error toast.

    """
    filename, lineno = _extract_error_location(exc)
    return json.dumps({
        "type": type(exc).__qualname__,
        "message": str(exc),
        "file": filename,
        "line": lineno,
    })
