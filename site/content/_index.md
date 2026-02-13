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

## The Bengal Ecosystem

A structured reactive stack — every layer written in pure Python for 3.14t free-threading.

| | | | |
|--:|---|---|---|
| **ᓚᘏᗢ** | [Bengal](https://github.com/lbliii/bengal) | Static site generator | [Docs](https://lbliii.github.io/bengal/) |
| **∿∿** | **Purr** | Content runtime ← You are here | — |
| **⌁⌁** | [Chirp](https://github.com/lbliii/chirp) | Web framework | [Docs](https://lbliii.github.io/chirp/) |
| **=^..^=** | [Pounce](https://github.com/lbliii/pounce) | ASGI server | [Docs](https://lbliii.github.io/pounce/) |
| **)彡** | [Kida](https://github.com/lbliii/kida) | Template engine | [Docs](https://lbliii.github.io/kida/) |
| **ฅᨐฅ** | [Patitas](https://github.com/lbliii/patitas) | Markdown parser | [Docs](https://lbliii.github.io/patitas/) |
| **⌾⌾⌾** | [Rosettes](https://github.com/lbliii/rosettes) | Syntax highlighter | [Docs](https://lbliii.github.io/rosettes/) |

Python-native. Free-threading ready. No npm required.

## Try It

Edit this file (`site/content/_index.md`) while `purr dev` is running and watch the browser update without a full reload.
