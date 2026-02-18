"""Logout route — POST /logout."""

from chirp import Redirect, Request, logout


path = "/logout"
nav_title = None  # No nav entry


async def post(request: Request):
    """Log out and redirect home."""
    logout()
    return Redirect("/")
