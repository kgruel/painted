# web — the painted public site

The public landing + guides + reference site for **painted**, built on **Astro**
with **React islands** (Phase 2 of `docs/dev/plans/2026-06-01-docs-system-design.md`).

**This is a separate publish pipeline.** It has its own Node toolchain, is **NOT**
part of `./dev check`, and the library never imports it — the package keeps its
zero-runtime-dependency invariant and this directory never touches it. The one place
`web/` and the library meet is the generated panels (below), and that seam is gated.

## The one load-bearing invariant

Anywhere the site shows painted's **actual output**, that output is **real library
output** — captured by `tools/outputgen.py` through `render_html` (cells → HTML) and
committed as `.html` under `src/generated/panels/`. The site is the load-bearing
dogfood: it shows what painted *actually renders*, not a recreation. The Design kit
(styles, hero) is a **cosmetic** recreation for brand/mocks **only** and must never
claim "this is what painted renders." Keep real-output surfaces on the real path.

## Layout — authored vs generated

| Path | Kind | Notes |
|------|------|-------|
| `src/pages/{index,walkthrough,reference}.astro` | **authored** | the three shipped pages; `walkthrough`/`reference` are pure `?raw` consumers of the panels |
| `src/layouts/Base.astro` | **authored** | shell: tokens + terminal defaults + font import |
| `src/components/PaintedSurface.jsx` | **vendored** | the hero island, verbatim from the Design kit |
| `src/styles/colors_and_type.css` | **vendored** | painted design tokens (from the Design kit); the ANSI-16 block is byte-exact to `core/_color.py` |
| `src/styles/fonts.css` | **authored** | self-hosted JetBrains Mono (see fonts, below) |
| `src/generated/panels/*.html` | **generated — do not hand-edit** | 32 real-output panels; see `src/generated/README.md` |

## Fixing / regenerating a panel

Panels are committed real output, not markup you edit by hand. To change one, change
its source (the demo or specimen) and regenerate:

```sh
./dev panels        # rewrites src/generated/panels in place (outputgen → committed HTML)
```

`./dev check`'s **outputgen tier** then verifies the panels match a fresh render — a
renderer change that forgets to regenerate fails the gate, so internal docs and the
site can't silently drift. The panel **set** (which demos/specimens, which zoom /
format / palette) is `PANELS` in `tools/outputgen.py`, not here.

- **Panels how-to + the drift gate:** `src/generated/README.md`
- **The whole docs/site data flow** (fragments, sentinels, outputgen, the site leg,
  what deploys): `docs/dev/docs-system-dataflow.md`

## Fonts

JetBrains Mono is **self-hosted** (full glyph coverage) via `src/styles/fonts.css`
serving `public/fonts/*.woff2`. The Google Fonts CDN `<link>` is intentionally gone:
its `css2` endpoint serves language subsets that **drop** box-drawing (U+2500–257F)
and block-elements (U+2580–259F) — exactly the glyphs painted's borders and wordmark
are built from — which broke alignment. See the rationale header in `fonts.css`.

## The Design kit (provenance)

Vendored from Claude Design (`painted-design-kit/`, "painted Design System-6.zip",
2026-06-02): `colors_and_type.css` and the `PaintedSurface` hero. When Design
re-iterates, re-vendor those two from the kit.

## Commands

```sh
npm run dev       # dev server, localhost:4321
npm run build     # static build → ./dist/ (gitignored)
npm run preview   # serve ./dist/ locally
```

## Not yet built

Guides as content collections, API tables, Pagefind search.
