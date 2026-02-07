"""Static export — pre-render the live app to HTML files.

Renders all routes (static content + dynamic Chirp routes) to plain HTML
files suitable for deployment to any static hosting service.

For content pages, this is equivalent to Bengal's existing build pipeline.
For dynamic routes, it pre-renders with default state (empty query params,
no session, etc.).
"""

class StaticExporter:
    """Exports a Purr application as static files.

    Iterates all registered routes (content + dynamic), renders each to HTML,
    and writes the output to the configured directory structure.

    Also handles:
    - Static asset copying with fingerprinting
    - Sitemap generation
    - 404 page rendering
    """

    # Phase 4: Implementation pending
