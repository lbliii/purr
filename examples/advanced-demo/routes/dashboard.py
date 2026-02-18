"""Dashboard route — protected, requires login."""

from chirp import Template, get_user, login_required


path = "/dashboard"
nav_title = "Dashboard"


@login_required
async def get(request):
    """Show user dashboard with links to premium content."""
    user = get_user()
    return Template("dashboard.html", title="Dashboard", user=user)
