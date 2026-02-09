---
title: Reactive Pipeline
description: How Purr's content-reactive system works
tags:
  - architecture
  - reactive
---

# Reactive Pipeline

Purr's headline feature is **surgical browser updates** when you edit content. Here's how it works under the hood.

## The Flow

When you save a Markdown file during `purr dev`:

1. **ContentWatcher** detects the file change via `watchfiles`
2. **Incremental parser** (Patitas) re-parses only the changed byte range
3. **AST differ** compares old and new document trees
4. **Reactive mapper** maps AST changes to affected template blocks
5. **Block recompiler** (Kida) recompiles only changed blocks
6. **SSE broadcaster** pushes Fragment updates to connected browsers
7. **HMR script** swaps the updated DOM elements in-place

The result: sub-100ms updates from keystroke to browser, with zero full page reloads.

If the fragment update path cannot resolve affected blocks (e.g., template introspection is unavailable), the pipeline falls back to pushing a `purr:refresh` event that triggers a full page reload — ensuring updates always reach the browser.

## Observability

Every stage is instrumented. Check `/__purr/stats` during dev for:

- Per-update timing breakdown (parse, diff, map, recompile, broadcast)
- Aggregate latency percentiles (p50, p95, p99)
- Event log summary

## Error Handling

When something goes wrong during a reactive update:

- **Template render errors** show a styled error overlay in the browser with source context, line highlighting, and a collapsible stack trace
- **Pipeline errors** broadcast a `purr:error` SSE event that renders a dismissible toast in the browser
- No more guessing from terminal output -- errors appear right where you're looking

## Performance Budget

The pipeline is designed for **< 50ms** end-to-end latency:

| Stage | Target | Technique |
|-------|--------|-----------|
| Parse | < 10ms | Incremental parsing (Patitas `parse_incremental`) |
| Diff | < 5ms | Positional AST comparison |
| Map | < 2ms | O(1) block metadata lookup |
| Recompile | < 25ms | Selective block recompilation (Kida) |
| Broadcast | < 10ms | Targeted SSE per subscriber |
