"""Auth routes — login, logout, load_user for AuthMiddleware."""

from dataclasses import dataclass

from chirp import Redirect, Request, Template, get_user, is_safe_url, login, logout
from chirp.security.passwords import hash_password, verify_password


@dataclass(frozen=True, slots=True)
class User:
    id: str
    name: str
    password_hash: str
    is_authenticated: bool = True


_DEMO_HASH = hash_password("password")
USERS: dict[str, User] = {
    "admin": User(id="admin", name="Admin", password_hash=_DEMO_HASH),
}


async def load_user(user_id: str) -> User | None:
    """Load user by ID — called by AuthMiddleware on each request."""
    return USERS.get(user_id)


path = "/login"
nav_title = "Log in"


async def get(request: Request):
    """Show login form."""
    return Template("login.html", title="Log in", error="")


async def post(request: Request):
    """Handle login form submission."""
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    user = USERS.get(username)
    if user and verify_password(password, user.password_hash):
        login(user)
        next_url = request.query.get("next", "/")
        if not is_safe_url(next_url):
            next_url = "/"
        return Redirect(next_url)

    return Template("login.html", title="Log in", error="Invalid username or password")
