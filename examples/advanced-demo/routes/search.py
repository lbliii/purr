"""Search route — filter site pages by query."""

from urllib.parse import urlencode

from chirp import Redirect, Request, Template

from purr import site as purr_site


path = "/search"
nav_title = "Search"


async def post(request: Request):
    """Accept POST from chirp check (form action); redirect to GET with query."""
    form = await request.form()
    q = form.get("q", "").strip()
    return Redirect("/search" + ("?" + urlencode({"q": q}) if q else ""))


async def get(request: Request):
    """Search content pages by title and content."""
    query = (request.query.get("q") or "").strip().lower()
    site = purr_site
    results: list[object] = []
    if query and site:
        for page in getattr(site, "pages", []) or []:
            title = str(getattr(page, "title", "") or "")
            content = str(getattr(page, "html_content", "") or "")
            if query in title.lower() or query in content.lower():
                results.append(
                    {
                        "title": title or getattr(page, "name", "Untitled"),
                        "href": getattr(page, "href", "#"),
                    }
                )
    return Template("search.html", title="Search", query=query or "", results=results)
