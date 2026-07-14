# painted — API Guide

A semantic renderer for the terminal, built on cell buffers: declare what your output means, and rendering decisions derive from it. Start at Level 0. Only escalate when you hit a trigger.

**You are here** in the abstraction chain:

<!-- docgen:begin frag:abstraction-chain -->
```
atoms (data)  →  engine (runtime)  →  painted (surface)  →  apps (CLI)
Fact, Spec        Tick, Vertex         Block, Lens          loops/hlab/strange-loops
```

Below painted in the monorepo: `libs/atoms/` defines Facts and Specs; `libs/engine/` produces Ticks and stores. Above: `apps/loops/`, `apps/hlab/`, and `apps/strange-loops/` use painted's entry points and lenses for all display. painted renders whatever comes out — it doesn't know about loops concepts, just declared meaning (roles, tags, severities), zoom levels, and terminal cells.
<!-- docgen:end -->

**Two concerns, one contract.** painted has a rendering library (Block, Style, compose, lenses, writer) and a CLI framework (run_cli, CliRunner, context detection, mode dispatch). The contract between them is `Block` — your lens produces Blocks, the framework delivers them. Levels 0-1 below are pure renderer. Level 2 is the CLI framework. Levels 3-4 are specialized delivery mechanisms.

---

## Level 0 — Explore data (Renderer)

**Trigger**: I have unfamiliar data and want a quick first look.

```python
from painted import paint

paint({"status": "ok", "items": 42})      # transcribes its declared shape
paint(data, zoom=Zoom.DETAILED)           # more detail
paint(data, zoom=Zoom.MINIMAL)            # one-liner
```

`paint()` transcribes what a value declares — dict → key/value, list → items, a
dataclass/Enum → its fields — recursively, and never invents a shape a value
didn't declare (a bare list is items, not a chart; that claim needs
`lens=chart_lens`). It's the recurring verb the whole stack renders through,
from this one-liner up to a full TUI — the same call, more fidelity at each
level. The right starting point 80% of the time.

**Don't reach for yet**: Block, join, border, run_cli.

---

## Level 1 — Compose layout (Renderer)

**Trigger**: I need custom layout — columns, borders, padding.

```python
from painted import Block, Style, join_horizontal, border, pad, print_block

left = Block.text("Name: Alice", Style(bold=True))
right = Block.text("Score: 98", Style(fg="green"))
row = join_horizontal(left, Block.text("  "), right)
print_block(border(pad(row, left=1, right=1)))
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
from painted import run_cli, Fidelity, Block

def renderer(data: dict, fidelity: Fidelity, width: int | None) -> Block:
    return status_view(data, zoom=fidelity.depth, width=width)

def fetch() -> dict:
    return {"status": "ok"}

run_cli(sys.argv[1:], renderer=renderer, fetch=fetch)
```

You provide `renderer(data, fidelity, width) → Block` — the renderer contract
(docs/RENDERER_CONTRACT_DESIGN.md): given only the fetched data, the compiled
disclosure spec, and the width offered at delivery time (`None` off a TTY —
natural sizing, never a fabricated column count) — and `fetch() → data`. The
framework handles zoom/format/mode automatically. Declaring neither `renderer=`
nor `render=` installs the framework's own transcription default, so
`run_cli(argv, fetch=fetch)` alone still renders something honest. The older
`render(ctx, data) → Block` shape (reading `ctx.width`/`ctx.zoom` off a full
`CliContext`) is still accepted as `render=` — a compatibility window, not a
capability tier: mode, TTY state, and lifecycle are host-selection material
that a semantic renderer never consumes (behavior that varies by destination
belongs in handlers and hosts, not the renderer). New code should reach for
`renderer=` first.

**The disclosure ladder** (`docs/FIDELITY_DESIGN.md`) — each rung additive; climbing never rewrites the rung below:

| Rung | You need | You write |
|------|----------|-----------|
| 0 | decent defaults | `paint(data)` — no fidelity at all |
| 1 | detail levels | `if fidelity.depth >= Zoom.DETAILED:` — `-q`/`-v`/`-vv` come free |
| 2 | a named facet | declare `tags=[Tag("thinking", "Show reasoning", implied_at=3)]`; gate with `fidelity.shows("thinking")` — the `--thinking` flag, its help entry, and the depth implication are generated |
| 3 | density control | pass `budgets=True`; read `fidelity.chars`/`fidelity.lines` — only now do `--max-chars`/`--max-lines` exist |
| 4 | structural disclosure | build a `Doc`; `doc_lens` applies the whole spec |

Depth is anonymous detail (the user's word is "verbose"); a tag is a named facet a user would ask for at low depth (`--thinking` at `-q`). `ctx.zoom` (on the legacy `render=` shape) is the rung-1 view of `ctx.fidelity` — not a compat shim, blessed permanently; under `renderer=` the same view is `fidelity.depth`. `depth_aliases={"brief": 0, "full": 3}` adds app-local depth spellings. The honesty rule: a flag exists only because a capability was declared, and a declared capability must change output.

The other two axes:
- **Format** (`--json`/`--plain`): ANSI (TTY default), PLAIN (pipe default), JSON
- **Mode** (`-i`/`--static`/`--live`): AUTO detects from TTY

Streaming: add `fetch_stream` for live updates. Mode flags follow the honesty rule too: `--live` exists only when `fetch_stream` is declared, and `-i` only with an INTERACTIVE handler or `live_delivery="surface"` *plus* `fetch_stream` (where it converges with `--live` onto the same alt-screen surface).

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
`painted.core` + `painted.views` + `painted.display` + `painted.publish` are the **semver-stable** library surface (removing or renaming an `__all__` name is semver-MAJOR, guarded by `tests/unit/test_public_api.py`); `painted.cli` + `painted.tui` are the **evolving** framework surface that may change across minor versions.
<!-- docgen:end -->
<!-- docgen:begin frag:width-contract#summary -->
width is a two-part contract: *width-aware* — wcwidth counts display columns, so a block's display width is not `len()`; and *honors-width* — a passed `width` is *exact*, clipping or padding by default (pass `wrap=Wrap.CHAR`/`Wrap.WORD` to reflow), omitted for natural sizing.
<!-- docgen:end -->
- **Style is composable**: `Style(fg="green", bold=True)`.
- **Zoom propagates**: render functions receive zoom level, bifurcate detail.
- **Format auto-detects**: TTY → ANSI, pipe → PLAIN.

## Diagnostics

Render the two surfaces every program already emits — log records and uncaught
tracebacks — instead of printing format strings. Both are opt-in and live at the
package root (not the CLI framework — a log handler and an excepthook aren't
argv-driven). See `docs/DIAGNOSTICS_DESIGN.md`.

```python
import logging, painted

logging.getLogger().addHandler(painted.PaintedHandler())  # records → styled Blocks
painted.install()                                          # uncaught tracebacks render too
```

- **`PaintedHandler`** — a `logging.Handler` that renders each record (timestamp,
  severity-styled level, logger, message, `extra` fields, `exc_info` traceback)
  disclosed by `zoom`. A renderer, not a formatter: `setFormatter` shapes the
  message string only; the structure stays painted's. Palette + color depth are
  snapshotted at construction, so worker-thread logs render identically. A log
  level is a *declared severity* — `DEFAULT_THRESHOLDS` maps `levelno` floors onto
  the closed `Severity` vocabulary; pass your own to change where lines fall.
- **`install()`** — routes `sys.excepthook` through `render_traceback`;
  `threads=True` also sets `threading.excepthook`. `KeyboardInterrupt` passes
  through untouched.
- **`render_traceback(exc, zoom, width, *, suppress=…)`** (from `painted.views`) —
  the underlying renderer, usable directly. An exception as a record tree: frames
  on a gutter rail, cause/context chains and groups as the tree. See the views
  guide.

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
    paint(data)
```

`Palette` — 5 semantic Style roles (success, warning, error, accent, muted), plus a `series` categorical ramp for visually separating N peers.
`IconSet` — named glyph slots (spinner, progress, tree, sparkline).
Both use ContextVar — scoped overrides via context manager.
`Capabilities` (`current_capabilities()`) is a sibling ambient channel for destination carriers — color/glyph/link — read by a renderer choosing between carriers (e.g. truecolor portrait vs. luminance glyph ramp), never for glyph fallback or color downsampling (those stay `IconSet`/`ColorDepth`'s job).

## Refs — denotation becomes a link

A **ref** is an opaque per-cell annotation: what a cell *refers to*, never how
it looks. Stamp it at construction (`Block.text("deploy ok", style,
ref="fact:01JQ8F")`); it survives every compose op and paint. Deliveries read
it: the TUI resolves clicks (`Surface.hit(x, y) → ref`), and a declared
`RefScheme` turns `scheme:value` refs into links — OSC 8 hyperlinks in ANSI,
`<a href>` in HTML:

```python
from painted import RefScheme, use_refs

use_refs(RefScheme("fact", lambda value: f"https://loops.dev/f/{value}"))
```

No declared scheme → refs stay inert in every delivery (painted never invents
URIs); scheme-less refs (`ref="sidebar"`) are the hit-testing idiom and stay
inert in link deliveries by design. See `docs/REFS_DESIGN.md`.

## Prompts — conversation as CLI grammar

`--force` and `Are you sure? [y/N]` are the same declaration at different
fidelities: one resolves from argv, one resolves interactively at a TTY.
Declare a prompt beside your tags and `run_cli` generates its flag, its
`-h` entry, and completion of its answer values — for free.

```python
from painted.cli import Confirm, Danger, Select, run_cli

def fetch(ctx):
    if ctx.ask("force"):
        ...

run_cli(
    args, render, fetch,
    prompts=[
        Confirm("force", "Force overwrite?", danger=Danger.SOFT),
        Select("scope", "Which store?", values=("local", "config", "all"),
               default="local"),
    ],
)
```

- **`Confirm`/`Select`/`Input`** — three domain shapes over one `Prompt[T]`
  primitive: a yes/no, a choice over an enumerable domain (`values=` or a
  declared `Vocabulary`), and free text (`parse=` maps `str → T`;
  `completer=` rides shell completion).
- **`ctx.ask(name)`** — the single door an answer comes through, memoized
  (fires at most once per run). One sentence: a Tag's answer is in
  `ctx.args`; a Prompt's answer is behind `ctx.ask`.
- **`--no-input`** — one framework flag, disabling all interactivity: every
  prompt resolves as if stdin were not a terminal (flag, then declared
  `default=`, then an honest refusal naming the flag).
- **`danger=`** — an ordered ceremony tier: `NONE` (Enter accepts the
  default), `SOFT` (an explicit key, no Enter-default), `HARD`
  (`Confirm`-only; type the declared `challenge=` to proceed — anything
  else resolves `False`, fail-closed).

Resolution never hangs and never invents an answer: a script with no flag
and no default gets a `ContractError` naming the exact flag that would
resolve it, not a silent default or a stalled pipe. See
`docs/PROMPTS_DESIGN.md`.
