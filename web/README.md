# web — the painted public site

Phase 2 of the docs-system plan (`docs/dev/plans/2026-06-01-docs-system-design.md`):
the public landing + guides + reference site for **painted**, built on **Astro**
with **React islands**. This is a **separate publish pipeline** — it has its own
Node toolchain and is **NOT** part of `./dev check` (the package keeps its
zero-runtime-dependency invariant; this directory never touches it).

## Status — scaffold slice

A thin vertical slice that **builds and serves**:

- `src/styles/colors_and_type.css` — the painted design tokens (81 custom props).
  **Bootstrap copy**, extracted + un-escaped from `painted Design System
  (standalone).html`. The ANSI-16 block is byte-exact to `core/_color.py`.
  *Replace wholesale when Claude Design ships the standalone `colors_and_type.css`.*
- `src/layouts/Base.astro` — the shell: tokens + terminal defaults (monospace,
  ink canvas, ligatures off).
- `src/components/HeroIsland.jsx` — **placeholder** hero island (`client:load`).
  Proves React hydration + tokens. *Swap for Design's designated, polished hero*
  (the no-cliffs CLI→TUI walkthrough or the system-monitor Surface).
- `src/pages/index.astro` — landing page wiring the above.

## Not yet built (next slices)

Reference panels (real painted output via the `outputgen` cells→HTML path),
guides as content collections, API tables, Pagefind search.

## Laning rule (load-bearing)

The Design kit is a **cosmetic recreation** of painted's look — for the hero,
brand, and mocks **only**. It must never claim "this is what painted renders."
Anywhere the site shows painted's actual output, that output comes from the
**real library** via `outputgen`. Keep `/reference` panels on the real path.

## Commands

```sh
npm run dev       # dev server, localhost:4321
npm run build     # static build → ./dist/
npm run preview   # serve ./dist/ locally
```
