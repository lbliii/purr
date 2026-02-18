"""Contact form — GET/POST with CSRF."""

from chirp import Redirect, Request, Template
from chirp.middleware.sessions import get_session


path = "/contact"
nav_title = "Contact"


async def get(request: Request):
    """Show contact form."""
    return Template("contact.html", title="Contact", error="", name="", email="", message="")


async def post(request: Request):
    """Handle contact form submission."""
    form = await request.form()
    name = form.get("name", "").strip()
    email = form.get("email", "").strip()
    message = form.get("message", "").strip()

    if not name or not email or not message:
        return Template(
            "contact.html",
            title="Contact",
            error="Please fill in name, email, and message.",
            name=name,
            email=email,
            message=message,
        )

    session = get_session()
    session["contact_name"] = name
    return Redirect("/thank-you")
