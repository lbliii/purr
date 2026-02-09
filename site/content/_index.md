---
title: Purr
description: A content-reactive runtime for Python 3.14t
---

# Welcome to Purr

Purr is a **content-reactive runtime** that unifies the Bengal ecosystem. Edit content, see the browser update surgically. Add dynamic routes alongside static pages. Deploy as static files or run as a live server.

## Three Modes

| Mode | Command | What it does |
|------|---------|-------------|
| **Dev** | `purr dev` | Reactive local development with HMR |
| **Build** | `purr build` | Static export to `dist/` |
| **Serve** | `purr serve` | Live production server via Pounce |

## The Stack

```
purr        Content runtime   (connects everything)
pounce      ASGI server       (serves apps)
chirp       Web framework     (serves HTML)
kida        Template engine   (renders HTML)
patitas     Markdown parser   (parses content)
rosettes    Syntax highlighter (highlights code)
bengal      Static site gen   (builds sites)
```

## Try It

Edit this file (`site/content/_index.md`) while `purr dev` is running and watch the browser update without a full reload.
