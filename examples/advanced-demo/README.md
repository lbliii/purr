# Purr Academy — Advanced Demo

A comprehensive demo site showcasing Purr's full potential: auth, gated content, search, contact form, and reactive dev mode.

## Features

- **Public content** — Getting started, API reference
- **Gated content** — Premium tutorials (login required)
- **Auth** — Login/logout with session + AuthMiddleware
- **Search** — Filter site pages by query
- **Contact form** — POST with CSRF protection
- **Dashboard** — Protected route with user info

## Prerequisites

Purr includes auth dependencies (`itsdangerous`, `argon2-cffi`) by default. Just install Purr:

```bash
pip install -e .   # or: uv sync (from purr root)
```

## Run

```bash
cd examples/advanced-demo
purr dev
```

Open http://127.0.0.1:3000

**Demo credentials:** admin / password

## Config

`purr.yaml` enables auth and configures:

- `auth: true` — Session + Auth + CSRF middleware
- `auth_load_user: auth:load_user` — Load user from routes/auth.py
- `session_secret` — Change in production
- `gated_metadata_key: gated` — Frontmatter key for protected pages

## Structure

```
content/          # Markdown pages (gated: true for premium)
templates/        # Kida templates
routes/           # Dynamic routes (auth, dashboard, search, contact)
static/           # CSS, JS
purr.yaml         # Purr config
bengal.toml       # Bengal site config
```
