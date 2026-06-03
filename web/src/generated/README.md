# Generated panels — do not edit by hand

The `.html` files under `panels/` are **real painted output** — captured from the
library by `tools/outputgen.py` and rendered through `render_html` (cells → HTML).
They are committed artifacts the Astro build imports via `?raw`, not hand-written
markup. This is the load-bearing dogfood: the site shows what painted actually
produces, not a recreation of it. Two sets live here:

- **28 panels = 7 monitor + 21 reference.** The `monitor_*` panels are the
  "no cliffs" walkthrough (`/walkthrough`), one dataset across the continuum. The
  rest are the reference catalog (`/reference`) — one real specimen per Design
  preview card, from `tools/reference_specimens.py`.

## Regenerate

Run from a **current painted library checkout on `main`** (where the demos,
`reference_specimens.py`, and outputgen live):

```sh
./dev panels <path-to>/web/src/generated/panels
```

> ⚠️ Do **not** run this from this `site` checkout. The site branch is decoupled
> and carries an older library snapshot **without `tools/reference_specimens.py`**,
> so `./dev panels` there would silently emit only the 7 monitor panels and drop
> all 21 reference ones. Always regenerate from an up-to-date `main` checkout and
> point `--emit-panels` at this directory.

Re-run whenever any of these change, or the panels will drift from what the
library actually renders:

- the demo (`demos/patterns/monitor.py`) or the specimens (`tools/reference_specimens.py`),
- the panel set (`PANELS` in `tools/outputgen.py`),
- the palette (`PAINTED_PALETTE` / `Palette.series`),
- the renderer (`render_html`, `_color`).

The panel **set** (which demos/specimens, which zoom/format/palette) is defined by
`PANELS` in the library, not here — this directory only holds the rendered output.
