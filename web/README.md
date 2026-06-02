# web — the painted public site

Phase 2 of the docs-system plan (`docs/dev/plans/2026-06-01-docs-system-design.md`):
the public landing + guides + reference site for **painted**, built on **Astro**
with **React islands**. This is a **separate publish pipeline** — it has its own
Node toolchain and is **NOT** part of `./dev check` (the package keeps its
zero-runtime-dependency invariant; this directory never touches it).

## Status — landing slice (real Design hero integrated)

A vertical slice that **builds and serves**, now on Claude Design's canonical kit:

- `src/styles/colors_and_type.css` — the painted design tokens (81 custom props).
  **Vendored from Claude Design** (`painted-design-kit/colors_and_type.css`,
  `painted Design System-6.zip`, 2026-06-02). The ANSI-16 block is byte-exact to
  `core/_color.py`. The Google-Fonts `@import` was removed; the face loads via a
  `<link>` in `Base.astro` (faster, no double-fetch — see the kit's `fonts/README.md`).
- `src/components/PaintedSurface.jsx` — **the designated hero**, vendored verbatim
  from the kit: a self-contained ESM React island (the system-monitor Surface),
  `import React` + `export default`, scoped keyboard, injects its own tokens.
  Mounted `client:visible` in `index.astro`. SSRs + hydrates.
- `src/layouts/Base.astro` — the shell: tokens + terminal defaults + the
  JetBrains Mono `<link>`.
- `src/pages/index.astro` — wordmark + tagline + the hero island.

Source of truth for the kit: `painted-design-kit/` (the Design package). When
Design re-iterates, re-vendor `colors_and_type.css` and `hero/PaintedSurface.jsx`.

## Not yet built (next slices)

- **Fonts hardening:** self-host via `@fontsource/jetbrains-mono` (no third-party
  request, no CLS) — currently the Google-Fonts CDN `<link>`.
- Reference panels (real painted output via the `outputgen` cells→HTML path),
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
