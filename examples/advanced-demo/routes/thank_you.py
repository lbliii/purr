"""Thank-you page after contact form submission."""

from chirp import Template
from chirp.middleware.sessions import get_session


path = "/thank-you"
nav_title = None


async def get(request):
    """Show thank-you message."""
    session = get_session()
    name = session.get("contact_name", "there")
    return Template("thank_you.html", title="Thank you", name=name)
