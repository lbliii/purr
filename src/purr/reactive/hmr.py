"""Hot module replacement — htmx SSE injection for dev mode.

Injects a small script into HTML responses that connects the browser to
Purr's SSE endpoint for reactive updates. Only active in dev mode.

The injected script:
1. Listens for ``fragment`` events (Chirp Fragment rendering)
2. Swaps the affected DOM element via the block's ID
3. Listens for ``purr:refresh`` events and reloads the page
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp.http.request import Request
    from chirp.http.response import Response, SSEResponse, StreamingResponse
    from chirp.middleware.protocol import Next

    type AnyResponse = Response | StreamingResponse | SSEResponse


# The script injected before </body> in dev mode.  It's intentionally
# minimal — no htmx dependency, just native EventSource.
_HMR_SCRIPT = """\
<script data-purr-hmr>
(function() {
  var page = location.pathname;
  var src = new EventSource('/__purr/events?page=' + encodeURIComponent(page));
  src.addEventListener('fragment', function(e) {
    var tmp = document.createElement('div');
    tmp.innerHTML = e.data;
    var el = tmp.firstElementChild;
    if (el && el.id) {
      var target = document.getElementById(el.id);
      if (target) target.outerHTML = el.outerHTML;
    }
    _dismissError();
  });
  src.addEventListener('purr:refresh', function() {
    location.reload();
  });
  src.addEventListener('purr:error', function(e) {
    try { var d = JSON.parse(e.data); _showError(d); } catch(x) {}
  });
  src.onerror = function() {
    setTimeout(function() { location.reload(); }, 2000);
  };
  function _showError(d) {
    _dismissError();
    var el = document.createElement('div');
    el.id = 'purr-error-toast';
    el.style.cssText = 'position:fixed;bottom:1rem;right:1rem;max-width:480px;'
      + 'background:#2d1010;border:1px solid #e74c3c;border-radius:8px;'
      + 'padding:1rem 1.25rem;font-family:ui-monospace,monospace;font-size:0.85rem;'
      + 'color:#f0a0a0;z-index:99999;box-shadow:0 4px 24px rgba(0,0,0,0.4);'
      + 'line-height:1.5;word-break:break-word';
    var title = document.createElement('strong');
    title.style.cssText = 'display:block;color:#e74c3c;margin-bottom:0.25rem';
    title.textContent = d.type || 'Error';
    var msg = document.createElement('div');
    msg.textContent = d.message || '';
    var loc = document.createElement('div');
    loc.style.cssText = 'margin-top:0.5rem;color:#9e9e9e;font-size:0.75rem';
    loc.textContent = (d.file || '') + (d.line ? ':' + d.line : '');
    var close = document.createElement('button');
    close.textContent = 'Dismiss';
    close.style.cssText = 'margin-top:0.75rem;padding:0.25rem 0.75rem;'
      + 'background:#3a1515;border:1px solid #e74c3c;border-radius:4px;'
      + 'color:#e0e0e0;cursor:pointer;font-family:inherit;font-size:0.8rem';
    close.onclick = _dismissError;
    el.appendChild(title);
    el.appendChild(msg);
    el.appendChild(loc);
    el.appendChild(close);
    document.body.appendChild(el);
  }
  function _dismissError() {
    var old = document.getElementById('purr-error-toast');
    if (old) old.remove();
  }
})();
</script>
"""


async def hmr_middleware(request: Request, next: Next) -> AnyResponse:
    """Chirp middleware that injects the HMR script into HTML responses.

    Only modifies responses with ``text/html`` content type. Injects
    the script tag just before ``</body>`` (or appends if no closing tag).

    """
    response = await next(request)

    # Only inject into regular (non-streaming, non-SSE) HTML responses
    if not hasattr(response, "body") or not hasattr(response, "content_type"):
        return response

    if "text/html" not in response.content_type:
        return response

    body = response.body
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    # Inject before </body> if present, otherwise append
    if "</body>" in body:
        body = body.replace("</body>", _HMR_SCRIPT + "</body>", 1)
    elif "</html>" in body:
        body = body.replace("</html>", _HMR_SCRIPT + "</html>", 1)
    else:
        body += _HMR_SCRIPT

    return replace(response, body=body)
