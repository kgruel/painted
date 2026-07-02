# painted

A semantic renderer for the terminal. You declare what your output *means* —
which fields matter at a glance, which are detail, which facets a reader
would ask for by name — and painted derives how to show it: how much detail,
what format, styled or plain, and which CLI flags exist at all. One dependency.

## What "semantic" means, concretely

Here's a deploy-status tool. The render function declares meaning in three
places: each service's *state* maps to a severity style, per-service latency
is a named facet called `timings`, and error detail belongs to zoom level 2.
It never mentions flags, pipes, JSON, or help text.

```python
import sys
from painted import Block, Style, Tag, join_vertical, run_cli
from painted.cli import CliContext

STATE_STYLE = {
    "ok": Style(fg="green"),
    "degraded": Style(fg="yellow"),
    "down": Style(fg="red", bold=True),
}

def fetch() -> dict:
    return {"services": [
        {"name": "api-gateway", "state": "ok", "replicas": "3/3", "ms": 12},
        {"name": "billing", "state": "degraded", "replicas": "2/3", "ms": 340},
        {"name": "search", "state": "ok", "replicas": "2/2", "ms": 28},
    ]}

def render(ctx: CliContext, data: dict) -> Block:
    rows = []
    for svc in data["services"]:
        line = f"{svc['state']:<9} {svc['name']:<14} {svc['replicas']}"
        if ctx.fidelity.shows("timings"):                # a named facet
            line += f"  {svc['ms']:>4}ms"
        rows.append(Block.text(line, STATE_STYLE[svc["state"]]))
        if ctx.zoom >= 2 and svc["state"] != "ok":       # detail level
            rows.append(Block.text("          last error: upstream timeout (2m ago)", Style(dim=True)))
    return join_vertical(*rows)

run_cli(
    sys.argv[1:], render=render, fetch=fetch,
    prog="deploys", description="Deployment status",
    tags=[Tag("timings", "Show per-service latency", implied_at=2)],
)
```

That's the whole program. Now watch the rendering decisions derive — every
output below is real captured output of the code above.

The default view shows what you declared to matter at a glance (on a TTY,
`ok` is green and `degraded` is yellow — the severity styles):

```console
$ deploys
ok        api-gateway    3/3
degraded  billing        2/3
ok        search         2/2
```

`-v` means zoom 2 — so the error detail you gated appears, and `timings`
switches on because you declared it implied at that depth:

```console
$ deploys -v
ok        api-gateway    3/3    12ms
degraded  billing        2/3   340ms
          last error: upstream timeout (2m ago)
ok        search         2/2    28ms
```

`--timings` exists as a flag *because* the Tag was declared — a reader can
ask for that one facet by name without the rest of the verbosity:

```console
$ deploys --timings
ok        api-gateway    3/3    12ms
degraded  billing        2/3   340ms
ok        search         2/2    28ms
```

The same declaration serializes — `render` isn't even called for this:

```console
$ deploys --json
{"services": [{"name": "api-gateway", "state": "ok", "replicas": "3/3", "ms": 12}, ...]}
```

A pipe gets plain text automatically — no ANSI garbage in `grep`:

```console
$ deploys | grep degraded
degraded  billing        2/3
```

And the help documents the surface you declared — nothing more:

```console
$ deploys -h
deploys

Deployment status

Layers (named facets)
  --timings  Show per-service latency

Zoom (what to show)
  -q, --quiet    Minimal output
  -v, --verbose  Detailed (-v) or full (-vv)

Format (serialization)
  --json   JSON output
  --plain  Plain text, no ANSI codes
...
```

Nothing was written twice, and none of it can drift: parsing, help, and TAB
completion are three reflections of the one declared parser — the flag under
`-h` is the flag that parses is the flag that completes (multi-command apps
get the zsh/bash glue from `run_app`'s auto-injected `completion` command).
That's the library's governing rule — the **honesty rule**: a flag exists
only because a capability was declared, and a declared capability must
change output. Nothing invented, nothing dead.

Styling toolkits make output beautiful; app frameworks compose widgets.
painted's job is the layer between: zoom, format, delivery mode, and the
flag surface itself all derive from what you declared the output to mean.

## Explore first

Zero declarations also works. `show()` is **exploration mode** — it guesses
a lens from the data's shape and adapts to context:

```python
from painted import paint

paint({"cpu": 67, "mem": 82, "disk": 45})
```

A TTY gets a styled sparkline summary; a pipe gets a plain one-liner
(`[3 values, 45–82]`); `show(data, format="json")` exports JSON. The guess
is a starting point for poking at data, not the API — when output matters,
you stop guessing: compose the Block yourself, or declare the CLI's
capabilities and let the surfaces derive.

## Enter anywhere

Every entry point uses the same building blocks. Pick the rung that fits
your problem — each rung is additive, and climbing never rewrites the rung
below. (The invariant is *monotonic enhancement*: day-one code stays
load-bearing forever.)

### Print styled output

Replace `print()` one call at a time. Auto-detects TTY — no ANSI garbage in pipes.

```python
from painted import Block, Style, print_block

block = Block.text("deploy OK", Style(fg="green", bold=True))
print_block(block)
```

<!-- TODO: tapes/styled.gif — print vs print_block contrast -->

### Compose

Blocks are immutable rectangles. Compose them with functions — no widget tree, no DOM.

```python
from painted import border, join_vertical, pad, ROUNDED

header = Block.text(" api-gateway ", Style(bold=True, reverse=True))
status = join_vertical(
    Block.text("  replicas: 2/3 ready", Style(fg="yellow")),
    Block.text("  /health:  200  12ms", Style(fg="green")),
)
card = border(join_vertical(header, status), chars=ROUNDED)
print_block(card)
```

<!-- TODO: tapes/compose.gif — bordered card output -->

### CLI harness

One render function, three output modes. Pipe gets static, TTY gets live updates,
`-i` gets full interactive.

```python
from painted import run_cli, CliContext, Block

def render(ctx: CliContext, data: dict) -> Block:
    # your render logic — returns a Block
    ...

def fetch() -> dict:
    return {"status": "ok", "replicas": 3}

run_cli(sys.argv[1:], render=render, fetch=fetch)
```

```bash
myapp              # auto-detect
myapp -q           # quiet (zoom 0)
myapp -v           # verbose (zoom 2)
myapp --json       # JSON output
myapp | grep ok    # plain text, no ANSI
```

<!-- TODO: tapes/zoom.gif — quiet/default/verbose spectrum -->

The flag surface grows only as you declare — the honesty rule again:

```python
run_cli(
    sys.argv[1:], render=render, fetch=fetch,
    tags=[Tag("thinking", "Show reasoning", implied_at=3)],  # generates --thinking
    depth_aliases={"brief": 0, "full": 3},                   # --brief / --full
    budgets=True,                                            # --max-chars / --max-lines
)
```

Gate content with `ctx.fidelity.shows("thinking")`; read `ctx.fidelity.chars`
for budgets. Add `fetch_stream=` for live updates (`--live` appears), and
`live_delivery="surface"` to upgrade sustained streams to an alt-screen
render loop (`-i` appears, converging with `--live`). Each rung is additive —
climbing never rewrites the rung below. For multi-command apps, `run_app`
routes subcommands through the same harness and injects a `completion`
command that emits the zsh/bash glue. The full consumer guide lives in
[`src/painted/README.md`](src/painted/README.md).

### Full TUI

Alt screen, keyboard input, async render loop, diff-flush. Subclass `Surface`,
override `render()` and `on_key()`.

```python
import asyncio
from painted import Block, Style, border
from painted.tui import Surface

class MyApp(Surface):
    def render(self):
        block = Block.text("Hello!", Style(fg="green"))
        border(block, title="Demo").paint(self._buf)

    def on_key(self, key: str):
        if key == "q":
            self.quit()

asyncio.run(MyApp().run())
```

<!-- TODO: tapes/tui.gif — alt screen flash with navigation -->

## Install

```bash
pip install painted
```

One dependency: [wcwidth](https://pypi.org/project/wcwidth/) (wide character display width).

## API

Two stability tiers: `painted.core` + `painted.views` + `painted.display` are
semver-stable (removing or renaming a public name is a major version —
`show()`'s removal at 1.0 is that pre-declared event); `painted.cli` +
`painted.tui` are the evolving framework surface and may change across minor
versions — pre-1.0, pin accordingly.

### Primitives

| Export | Purpose |
|--------|---------|
| `Cell` / `Style` | Atomic display unit (char + style, frozen) |
| `Span` / `Line` | Styled text with display-width awareness |
| `Block` | Immutable rectangle of cells for composition |

### Composition

| Export | Purpose |
|--------|---------|
| `join_horizontal` / `join_vertical` | Combine Blocks |
| `pad` / `border` / `truncate` | Transform Blocks |
| `BorderChars` | ROUNDED, HEAVY, DOUBLE, LIGHT, ASCII presets |

### Display

| Export | Purpose |
|--------|---------|
| `paint(data)` | Zero-config display; transcribes any value onto the surface |
| `print_block(block)` | Print a Block to stdout (TTY-aware) |
| `run_cli(args, render=, fetch=, ...)` | CLI harness: zoom/mode/format, plus declared `tags=`, `depth_aliases=`, `budgets=`, `fetch_stream=`, `live_delivery=` |
| `run_app(argv, commands)` | Multi-command routing; each `AppCommand` handler calls `run_cli` |

### Views (`painted.views`)

| Export | Purpose |
|--------|---------|
| `shape_lens` | Auto-dispatch for exploration (numeric → chart, hierarchical → tree) |
| `tree_lens` / `chart_lens` | Explicit tree and chart strategies |
| `list_view` / `table` / `text_input` | Stateful interactive components |
| `spinner` / `progress_bar` / `sparkline` | Animation and data viz |

### TUI (`painted.tui`)

| Export | Purpose |
|--------|---------|
| `Surface` | Alt screen, keyboard, resize, diff-flush render loop |
| `Layer` | Modal stack: `Stay` / `Pop` / `Push` / `Quit` |
| `Buffer` / `BufferView` | 2D cell grid with region clipping |

### Aesthetic

| Export | Purpose |
|--------|---------|
| `Palette` | 5 semantic Style roles (success, warning, error, accent, muted) + a `series` categorical ramp |
| `IconSet` | Glyph vocabulary with ASCII fallback |

## License

MIT
