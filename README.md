# painted

One library. Print to TUI. One dependency.

```python
from painted import paint

paint({"cpu": 67, "mem": 82, "disk": 45})
```

TTY gets styled output. Pipe gets plain text. Same data, same function —
`paint()` transcribes what the value declares, and it's the same verb every
layer up the stack renders through.

<!-- TODO: tapes/hero.gif — paint() in TTY and pipe contexts -->

## Enter anywhere

Every entry point uses the same building blocks. Pick the one that fits your problem —
you never hand over control, and there's no cliff between them.

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

The flag surface grows only as you declare capabilities — a flag exists only
because the app declared it, and a declared capability must change output:

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
routes subcommands through the same harness. The full consumer guide lives in
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
