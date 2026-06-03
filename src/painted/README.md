# painted — API Guide

Terminal UI framework built on cell buffers. Start at Level 0. Only escalate when you hit a trigger.

**You are here** in the abstraction chain:

<!-- docgen:begin frag:abstraction-chain -->
```
atoms (data)  →  engine (runtime)  →  painted (surface)  →  apps (CLI)
Fact, Spec        Tick, Vertex         Block, Lens          loops/hlab/strange-loops
```

Below painted in the monorepo: `libs/atoms/` defines Facts and Specs; `libs/engine/` produces Ticks and stores. Above: `apps/loops/`, `apps/hlab/`, and `apps/strange-loops/` use painted's entry points and lenses for all display. painted renders whatever comes out — it doesn't know about loops concepts, just data shapes, zoom levels, and terminal cells.
<!-- docgen:end -->

**Two concerns, one contract.** painted has a rendering library (Block, Style, compose, lenses, writer) and a CLI framework (run_cli, CliRunner, context detection, mode dispatch). The contract between them is `Block` — your lens produces Blocks, the framework delivers them. Levels 0-1 below are pure renderer. Level 2 is the CLI framework. Levels 3-4 are specialized delivery mechanisms.

---

## Level 0 — Display data (Renderer)

**Trigger**: I have data and want it to look decent in a terminal.

```python
from painted import show

show({"status": "ok", "items": 42})       # auto-formats by shape
show(data, zoom=Zoom.DETAILED)            # more detail
show(data, zoom=Zoom.MINIMAL)             # one-liner
```

`show()` auto-dispatches by data shape: dict → key-value, list → items, numeric → chart. This is the right starting point 80% of the time.

**Don't reach for yet**: Block, join, border, run_cli.

---

## Level 1 — Compose layout (Renderer)

**Trigger**: I need custom layout — columns, borders, padding.

```python
from painted import Block, Style, join_horizontal, border, pad, print_block

left = Block.text("Name: Alice", Style(bold=True))
right = Block.text("Score: 98", Style(fg="green"))
row = join_horizontal(left, Block.text("  "), right)
print_block(border(pad(row, 1)))
```

Key types:
- `Block` — immutable rectangle of cells. `Block.text()`, `Block.empty(w, h)`.
- `join_vertical`, `join_horizontal` — compose Blocks.
- `border`, `pad`, `truncate` — transform Blocks.
- `Style` — `fg`, `bg`, `bold`, `italic`, `underline`, `reverse`, `dim`. Composable.
- `Span` — text + style, width-aware. `Line` — tuple of Spans.

All immutable. All return new Blocks. Still just printing — no state, no framework.

**Don't reach for yet**: run_cli, Surface, Layer.

---

## Level 2 — CLI tool (Framework)

**Trigger**: I need `-v`/`-q`, `--json`, pipe detection, help text. This is where you cross from the rendering library into the CLI framework.

```python
from painted import run_cli, CliContext, Block

def render(ctx: CliContext, data: dict) -> Block:
    return status_view(data, zoom=ctx.zoom, width=ctx.width)

def fetch() -> dict:
    return {"status": "ok"}

run_cli(sys.argv[1:], render=render, fetch=fetch)
```

You provide `render(ctx, data) → Block` and `fetch() → data`. The framework handles zoom/format/mode automatically.

Three orthogonal dimensions:
- **Fidelity** (`-q`/`-v`/`-vv`): `ctx.fidelity` is the canonical field — `depth` (0–3), plus optional `visible` tag set and `chars`/`lines` density budgets. `ctx.zoom` returns `Zoom(fidelity.depth)` for backward compat.
- **Format** (`--json`/`--plain`): ANSI (TTY default), PLAIN (pipe default), JSON
- **Mode** (`-i`/`--static`/`--live`): AUTO detects from TTY

Streaming: add `fetch_stream` for live updates.

**Don't reach for yet**: Surface, Layer, InPlaceRenderer (unless you need custom animation outside the CLI harness).

---

## Level 3 — Live animation (Delivery)

**Trigger**: I need progress updates without alt-screen, outside the CLI harness.

```python
from painted import InPlaceRenderer, Block, Style
import time

with InPlaceRenderer() as r:
    for i in range(100):
        r.render(Block.text(f"Progress: {i}%", Style()))
        time.sleep(0.05)
    r.finalize(Block.text("Done!", Style(fg="green")))
```

Cursor-controlled in-place rewriting. Note: `run_cli` with `fetch_stream` already does this — only use `InPlaceRenderer` directly for custom animation outside the CLI harness.

**Don't reach for yet**: Surface, Layer.

---

## Level 4 — Interactive TUI (Delivery)

**Trigger**: I need keyboard input, full-screen, modal dialogs.

**Most tools don't need this.** Exhaust levels 0–3 first.

See `tui/CLAUDE.md` for the interactive app subsystem.

---

## Key invariants

- **Frozen types**: all types are immutable. Create new instances, don't mutate.
<!-- docgen:begin frag:stability-tiers#summary -->
`painted.core` + `painted.views` are the **semver-stable** library surface (removing or renaming an `__all__` name is semver-MAJOR, guarded by `tests/unit/test_public_api.py`); `painted.cli` + `painted.tui` are the **evolving** framework surface that may change across minor versions.
<!-- docgen:end -->
<!-- docgen:begin frag:width-contract#summary -->
width is a two-part contract: *width-aware* — wcwidth counts display columns, so a block's display width is not `len()`; and *honors-width* — a passed `width` is *exact*, clipping or padding by default (pass `wrap=Wrap.CHAR`/`Wrap.WORD` to reflow), omitted for natural sizing.
<!-- docgen:end -->
- **Style is composable**: `Style(fg="green", bold=True)`.
- **Zoom propagates**: render functions receive zoom level, bifurcate detail.
- **Format auto-detects**: TTY → ANSI, pipe → PLAIN.

## Data rendering

For lenses (auto-dispatch, tree, chart, flame) and components (spinner, progress, list, table, text input, data explorer):

```python
from painted.views import shape_lens, tree_lens, chart_lens, flame_lens
from painted.views import sparkline, sparkline_with_range
from painted.views import spinner, list_view, progress_bar, table, text_input, data_explorer
from painted.views import render_big, BigTextFormat
```

See `views/CLAUDE.md` for details.

## Aesthetic customization

```python
from painted import use_palette, NORD_PALETTE, use_icons, ASCII_ICONS

use_palette(NORD_PALETTE)   # set globally
use_icons(ASCII_ICONS)      # set globally

with use_palette(NORD_PALETTE):  # or scoped override
    show(data)
```

`Palette` — 5 semantic Style roles (success, warning, error, accent, muted), plus a `series` categorical ramp for visually separating N peers.
`IconSet` — named glyph slots (spinner, progress, tree, sparkline).
Both use ContextVar — scoped overrides via context manager.
