# Generated panels — do not edit by hand

The `.html` files under `panels/` are **real painted output** — captured from the
library by `tools/outputgen.py` and rendered through `render_html` (cells → HTML).
They are committed artifacts the Astro build imports via `?raw`, not hand-written
markup. This is the load-bearing dogfood: the site shows what painted actually
produces, not a recreation of it. Two sets live here:

- **32 panels = 7 monitor + 21 reference + 4 landing.** The `monitor_*` panels are
  the monotonic-enhancement walkthrough (`/walkthrough`), one dataset across the continuum.
  The reference catalog (`/reference`) is one real specimen per Design preview card,
  from `tools/reference_specimens.py`. The 4 landing panels (`hero`, `door_*`) are
  the front door (`/`), from `tools/landing_specimens.py`.

## Regenerate

`web/` lives in the monorepo, so regeneration is one in-repo command from the
repo root — this directory is the default target:

```sh
./dev panels        # rewrites web/src/generated/panels in place
```

`./dev check` then verifies these fragments match a fresh render — the **same**
`outputgen --check` that gates the doc sentinels also checks the panels, so a
renderer change that forgets to regenerate fails the gate. Internal docs and the
external site regenerate from one library and can't silently drift.

Re-run whenever any of these change (or the gate will flag it):

- the demo (`demos/patterns/monitor.py`) or the specimens (`tools/reference_specimens.py`),
- the panel set (`PANELS` in `tools/outputgen.py`),
- the palette (`PAINTED_PALETTE` / `Palette.series`),
- the renderer (`render_html`, `_color`).

The panel **set** (which demos/specimens, which zoom/format/palette) is defined by
`PANELS` in the library, not here — this directory only holds the rendered output.
