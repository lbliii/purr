# Purr Advanced Demo Site Plan

## Goal

Create a comprehensive demo site that demonstrates Purr's full potential: content-reactive dev mode, static export, authentication, gated content, search, forms, and dynamic routes. Serves as both a reference implementation and a "kitchen sink" for the Bengal ecosystem.

---

## 1. Demo Concept: "Purr Academy"

A documentation/knowledge-base site with:

- **Public content** — Getting started, API reference, community
- **Gated content** — Premium tutorials, advanced guides (require login)
- **Dynamic features** — Search, login/logout, user dashboard, contact form
- **Reactive dev** — Edit Markdown, see changes instantly (no reload)

---

## 2. Site Structure

```
examples/advanced-demo/
├── purr.yaml              # Config with auth enabled
├── content/
│   ├── _index.md          # Home (public)
│   ├── docs/
│   │   ├── _index.md      # Docs index (public)
│   │   ├── getting-started.md
│   │   └── api-reference.md
│   └── premium/           # Gated section
│       ├── _index.md      # Premium hub (gated)
│       ├── advanced-tutorials.md
│       └── deep-dives.md
├── templates/
│   ├── base.html          # Layout with nav, auth state
│   ├── page.html
│   ├── index.html
│   ├── login.html
│   └── dashboard.html
├── routes/
│   ├── __init__.py
│   ├── auth.py            # /login, /logout
│   ├── dashboard.py       # /dashboard (protected)
│   ├── search.py          # /search (GET, htmx)
│   └── contact.py         # /contact (form + CSRF)
├── static/
│   ├── css/
│   └── js/
└── README.md
```

---

## 3. Features to Showcase

| Feature | Implementation | Purr/Chirp Support |
|---------|----------------|-------------------|
| **Auth (login/logout)** | SessionMiddleware + AuthMiddleware | Chirp has it; Purr needs config hook |
| **Gated content** | Frontmatter `gated: true` + `@login_required` on handler | Purr ContentRouter enhancement |
| **Search** | GET route, htmx `hx-get`, filter `site.pages` by query | Works today via routes/ |
| **Contact form** | POST route, `form_or_errors`, CSRF | Chirp forms + CSRF; Purr needs CSRF middleware |
| **Dashboard** | Protected route, `get_user()` | Works via routes/ + auth |
| **Reactive dev** | File watcher, SSE, block updates | Works today |
| **Static export** | `purr build` | Works; gated pages → login redirect or 404 |
| **Navigation** | Nav shows Login/Logout based on auth | `current_user` global in templates |

---

## 4. Purr Changes Required

### 4.1 Auth and Session Middleware (New)

**Config extension** in `purr/config.py`:

```python
# Optional new fields
auth: bool = False
auth_load_user: str | None = None  # "routes.auth:load_user"
session_secret: str | None = None
```

**App wiring** in `purr/app.py`:

- When `config.auth` is True:
  - Add `SessionMiddleware(SessionConfig(secret_key=...))`
  - Add `AuthMiddleware(AuthConfig(load_user=...))`
  - Resolve `load_user` from `config.auth_load_user` (e.g. `routes.auth:load_user`)

**Dependencies:** `chirp[sessions,auth]` as optional extras when auth enabled.

### 4.2 Gated Content Support

**Option B — Handler wrapping:** When registering content routes, if `page.metadata.get("gated")` is True, wrap the handler with `@login_required`. ContentRouter's `_make_page_handler` can wrap: `handler = login_required(handler)` when gated.

**Config:** `gated_metadata_key: str = "gated"` (frontmatter key to check).

### 4.3 CSRF for Forms

Chirp has `CSRFMiddleware`. Purr adds it when `config.auth` is True (sessions required for CSRF tokens).

---

## 5. Content and Frontmatter

**Public page** (`content/docs/getting-started.md`):

```yaml
---
title: Getting Started
---
```

**Gated page** (`content/premium/advanced-tutorials.md`):

```yaml
---
title: Advanced Tutorials
gated: true
---
```

---

## 6. Routes Implementation

### 6.1 `routes/auth.py`

- `GET /login` — Render login form
- `POST /login` — Validate credentials, `login(user)`, redirect to `?next=` or `/`
- `POST /logout` — `logout()`, redirect to `/`
- `load_user(user_id)` — For AuthMiddleware (in-memory or SQLite for demo)

### 6.2 `routes/dashboard.py`

- `GET /dashboard` — `@login_required`, show user info + links to gated content

### 6.3 `routes/search.py`

- `GET /search` — Query param `q`, filter `site.pages` by title/content, return `Template` or `Fragment` for htmx

### 6.4 `routes/contact.py`

- `GET /contact` — Contact form
- `POST /contact` — `form_or_errors`, validate, flash message, redirect

---

## 7. Template Integration

**Base template** receives from Purr/Chirp:

- `site` — Bengal site (pages, sections)
- `page` — Current page (content routes)
- `current_user` — From Chirp auth (when middleware active)
- `dynamic_routes` — Nav entries for routes/

**Nav logic:**

```html
{% if current_user %}
  <a href="/dashboard">Dashboard</a>
  <form action="/logout" method="post">...</form>
{% else %}
  <a href="/login">Log in</a>
{% end %}
```

---

## 8. Static Export Behavior

For `purr build`:

- **Public pages** — Rendered as static HTML
- **Gated pages** — Render a "Log in to view" placeholder or redirect to `/login`
- **Dynamic routes** — Pre-rendered with default state (login form, empty search)

**Note:** `purr serve` is required for full auth and dynamic features. Static export produces a shell; auth-protected content is a placeholder.

---

## 9. Implementation Phases

### Phase 1 — Purr Auth Support
- Add `auth`, `auth_load_user`, `session_secret` to PurrConfig
- Add `_wire_auth_middleware()` when auth enabled
- Add `chirp[sessions,auth]` to optional deps or document in demo README

### Phase 2 — Gated Content
- Add `gated_metadata_key` to config
- In ContentRouter, wrap handler with `login_required` when `page.metadata.get(gated_metadata_key)` is truthy

### Phase 3 — Demo Scaffold
- Create `examples/advanced-demo/` with content, templates, routes
- Implement auth, dashboard, search, contact
- Add README with run instructions

### Phase 4 — Polish
- CSRF for contact form
- Error handling, flash messages
- Responsive theme

---

## 10. File Summary

| File | Purpose |
|------|---------|
| `purr/src/purr/config.py` | Add auth, session, gated config fields |
| `purr/src/purr/app.py` | Wire auth middleware, CSRF when enabled |
| `purr/src/purr/content/router.py` | Wrap gated page handlers with `login_required` |
| `examples/advanced-demo/*` | Full demo site |

---

## 11. Out of Scope (Future)

- **Database-backed users** — Demo uses in-memory; real apps would use chirp.data
- **Role-based access** — Single "logged in" vs "anonymous" for simplicity
- **AI search** — Could add later with chirp[ai]
- **Real-time collaboration** — Beyond current SSE use case
