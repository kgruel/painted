# Generated panels — do not edit by hand

The `.html` files under `panels/` are **real painted output** — captured from the
library's demos by `tools/outputgen.py` and rendered through `render_html`
(cells → HTML). They are committed artifacts the Astro build imports via `?raw`,
not hand-written markup. This is the load-bearing dogfood: the site shows what
painted actually produces, not a recreation of it.

## Regenerate

From the **painted library checkout** (where the demos + outputgen live):

```sh
./dev panels <path-to>/web/src/generated/panels
```

Re-run whenever any of these change, or the panels will drift from what the
library actually renders:

- the demo (`demos/patterns/monitor.py`),
- the panel set (`PANELS` in `tools/outputgen.py`),
- the palette (`PAINTED_PALETTE` / `Palette.series`),
- the renderer (`render_html`, `_color`).

The panel **set** (which demos, which zoom/format/palette) is defined by `PANELS`
in the library, not here — this directory only holds the rendered output.
