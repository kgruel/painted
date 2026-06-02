# painted — terminal rendering library

Terminal UI framework built on cell buffers. Start at Level 0. Only escalate when you hit a trigger.

**You are here** in the abstraction chain:

```
atoms (data)  →  engine (runtime)  →  painted (surface)  →  apps (CLI)
Fact, Spec        Tick, Vertex         Block, Lens, run_cli   loops/hlab/strange-loops
```

painted is consumed by every app in the monorepo. It doesn't know about loops concepts — just data shapes, zoom levels, and terminal cells.

**Two audiences**: If you're *using* painted in an app, see `src/painted/CLAUDE.md` for the consumer API guide. This file is for *contributing to* painted itself.

---

## Level 0 — Build and test

**Trigger**: I need to make a change to painted.

```bash
./dev check              # 10-tier gate: arch → lint → smoke → unit → property → appearance → integration → cohesion → outputgen → docs
./dev docs [--link|--check]  # assemble fragment bodies into surfaces; manage README↔CLAUDE.md symlinks
./dev test [-v]          # pytest wrapper, passthrough args
./dev lint               # ty check + ruff format check
./dev cov [--html]       # coverage report (not gated — informational; ~88% today)
./dev fmt                # auto-format (ruff)
```

`./dev check` must pass before any commit. Gate ordering: architecture checks first, then lint, then tests. If structure is wrong, everything else is noise.

**Don't reach for yet**: Internal module structure, rendering pipeline.

---

## Level 1 — Understand the stack

**Trigger**: I need to know where to make a change.

**Two concerns, one contract.** painted contains two distinct subsystems that share `Block` as their contract:

1. **The Renderer** — cells, styled text, blocks, composition, lenses, writer. Pure library code that turns data into terminal pixels. No knowledge of CLI args, modes, or dispatch.

2. **The CLI Framework** — argument parsing, context detection, mode dispatch, lifecycle management. Sits on top of the renderer. Connects user intent (`-v`, `--json`, pipe detection) to rendering.

They live in one package because CLI and TUI are fidelity levels of the same lens — not different apps. But the boundary is real: `core/fidelity.py` has zero module-level imports from painted's rendering modules. All imports are lazy, inside functions.

**The Renderer** (bottom to top):

```
Cell / Span / Line          # atomic units — one character, styled text, row
Block                       # immutable rectangle of cells — the universal type
compose / border / pad      # layout operations on Blocks
writer / InPlaceRenderer    # delivery: dump to stdout or cursor-controlled rewrite
```

**The CLI Framework** (on top of the renderer):

```
core/fidelity.py            # run_cli — zoom/mode/format parsing, context detection, dispatch
cli/app_runner.py           # run_app — multi-command routing through run_cli
```

**The TUI Subsystem** (a separate interactive delivery mechanism):

```
Surface + Layer             # alt-screen TUI with keyboard + diff rendering
```

**Module map** (grouped by concern):

| Concern | Module | Responsibility |
|---------|--------|---------------|
| Renderer | `core/cell.py` | Cell, Style, EMPTY_CELL |
| Renderer | `core/span.py` | Span, Line |
| Renderer | `core/block.py` | Block, Wrap |
| Renderer | `core/compose.py` | join, pad, border, truncate, Align |
| Renderer | `core/writer.py` | Writer, ColorDepth, print_block |
| Renderer | `inplace.py` | InPlaceRenderer |
| Renderer | `palette.py` | Palette (5 semantic Style roles), presets |
| Renderer | `icon_set.py` | IconSet (glyph vocabulary), ASCII fallback |
| Renderer | `views/record.py` | record_line, PayloadLens, GutterFn |
| Renderer | `views/lens/` | shape_lens, tree_lens, chart_lens, flame_lens |
| Renderer | `views/components/` | Stateful view components (spinner, progress, list, table, etc.) |
| Renderer | `views/` | Public view-layer namespace (re-exports lenses + components) |
| Framework | `core/fidelity.py` | Zoom, OutputMode, Format, CliContext, run_cli |
| Framework | `cli/app_runner.py` | AppCommand, run_app (multi-command dispatch) |
| TUI | `tui/` | Surface, Layer, Focus, Search, Buffer, KeyboardInput |

**Don't reach for yet**: record_line internals, TUI subsystem, mouse protocol.

---

## Level 2 — Key subsystems

**Trigger**: I need to modify rendering behavior, the CLI harness, or a component.

**`run_cli` flow** (`core/fidelity.py`):
1. Create `CliRunner(render, fetch, ...)` internally
2. Intercept `-h`/`--help` → painted help with zoom awareness
3. Parse framework args (`-q`, `-v`, `-vv`, `--json`, `--plain`, `--static`, `--live`, `-i`)
4. `detect_context()` resolves Zoom/Mode/Format from args and TTY state
5. Dispatch by mode: STATIC (`print_block`) → LIVE (`InPlaceRenderer`) → INTERACTIVE (custom handler)

**`record_line` pattern** (`views/record.py`):
- `record_line()` owns structure, `PayloadLens` interprets domain content
- Lens contract: return summary (str or styled Block). No multiline.
- `record_line` handles continuation lines at DETAILED (well-known keys) and FULL (all fields)
- Gutter contract: continuous vertical rail, never breaks. Color encodes ONE dimension.

**Component pattern** (`views/components/`):
- Frozen `State` dataclass + pure `render_fn(state, ...) → Block`
- State created via constructor, updated via `dataclasses.replace()`
- Components are stateless renderers — the caller owns state transitions

**Don't reach for yet**: TUI Surface internals, mouse protocol, viewport scroll math.

---

## Level 3 — TUI and interactive

**Trigger**: I need to modify the full-screen interactive subsystem.

See `tui/CLAUDE.md` for the interactive app primitives (Surface, Layer, Focus, Search). See `views/CLAUDE.md` for the data rendering components. See `views/components/CLAUDE.md` for internal implementation details.

Key patterns:
- Surface diff-renders: only changed cells written to terminal
- Layer stack: top handles keys, all render bottom-to-top. Base layer never pops.
- `Emit` is the feedback boundary — Surface emits observations that become Facts upstream
- TestSurface replays keys and captures frames — no real terminal needed

---

## Key invariants

- All state types frozen. Components follow `State + render_fn(state, ...) → Block`.
- **Stability tiers** (one package, differential guarantees): `painted.core` + `painted.views` are the **semver-stable** library surface — a renderer is a thing you *call*, so its surface is held maximally stable. Removing or renaming any name in their `__all__` is a semver-MAJOR break, guarded by `tests/unit/test_public_api.py` (additions are fine — extend the snapshot when you intend to commit to them). `painted.cli` + `painted.tui` are the **evolving** framework surface — they *call you*, and churn as apps' needs change. This resolves the library-vs-framework version tension without splitting the package.
- Surface diff-renders: only changed cells written to terminal.
- `shape_lens` auto-dispatches by data shape: numeric → chart, hierarchical → tree, else built-in rendering.
- Width is a two-part contract, both tested in `tests/property/`. **Width-aware**: wcwidth measures display columns, so display width ≠ `len()` (emoji/CJK). **Honors width**: a passed `width` is *exact* (`block.width == width`) — too-wide content is clipped (padded if short) to that width by default; pass `wrap=Wrap.CHAR`/`WORD` to reflow into more rows instead. Omit `width` for natural (content) sizing. Exactness is what lets composition subdivide a width budget and trust the pieces tile; `fit_to_width` is the block-level realization (horizontal-only — it clips, never reflows).
- Style is composable: `Style(fg="green", bold=True)`.
- Zero runtime dependencies beyond `wcwidth` (the single vetted exception, for display-width measurement). Enforced by `test_runtime_imports_are_stdlib_or_allowlisted`.

## Documentation

```
docs/
  ARCHITECTURE.md     # Stack visualization, data flow, layer pattern
  PRIMITIVES.md       # Quick reference for all primitives
  DATA_PATTERNS.md    # Frozen state + pure functions patterns
  MOUSE.md            # Terminal mouse protocol research
  VIEWPORT_DESIGN.md  # Scroll state management
  ZOOM_PATTERNS.md    # Lens zoom propagation patterns
  MODE_RESOLUTION.md  # AUTO mode collapse rules, capability filtering
  DEMO_PATTERNS.md    # TUI app pattern, demo organization
```
