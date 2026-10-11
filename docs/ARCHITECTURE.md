# painted Architecture

Data-flow reference for painted — a semantic renderer for the terminal, built on cell buffers.

Subordinate to [RENDER_MODEL.md](RENDER_MODEL.md), the ratified conceptual
model (the semantic-renderer ladder, the dual allocation contract, the eight
laws). This page describes implementation structure and data flow; where
vocabulary differs, the model's glossary governs.

## The Stack

```
┌─────────────────────────────────────────────────────────────┐
│  Terminal                                                   │
│  ANSI escape sequences in, keyboard bytes out               │
├─────────────────────────────────────────────────────────────┤
│  Writer                                                     │
│  Translates Cell changes → ANSI sequences                   │
│  Detects terminal size, controls mouse mode                 │
├─────────────────────────────────────────────────────────────┤
│  Buffer (diff engine)                                       │
│  2D grid of Cells                                           │
│  Compares current vs previous, emits only changes           │
├─────────────────────────────────────────────────────────────┤
│  Block / Compose                                            │
│  Immutable rectangles of Cells                              │
│  join_vertical, join_horizontal, pad, border, truncate      │
├─────────────────────────────────────────────────────────────┤
│  Span / Line                                                │
│  Styled text primitives                                     │
│  Span: text + style, Line: sequence of Spans                │
├─────────────────────────────────────────────────────────────┤
│  Cell / Style                                               │
│  Atomic unit: one character + one style                     │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### Render Path (State → Terminal)

```
AppState
    │
    ▼
render(state) ─────────────► Blocks
    │                           │
    │                           ▼
    │                      compose (join, pad, border)
    │                           │
    │                           ▼
    │                      Block.paint(buffer, x, y)
    │                           │
    ▼                           ▼
Buffer (current)           Cells written to grid
    │
    ▼
diff(previous, current)
    │
    ▼
Writer.write_cell(x, y, cell) ──► ANSI sequences
    │
    ▼
Terminal
```

### Input Path (Terminal → State)

```
Terminal
    │
    ▼
KeyboardInput.read() ──────► key: str
    │
    ▼
Surface.on_key(key)
    │
    ▼
process_key(key, state, ...) ─► Layer stack routing
    │                              │
    │                              ▼
    │                         top_layer.handle(key, layer_state, app_state)
    │                              │
    │                              ▼
    │                         (new_layer_state, new_app_state, action)
    │                              │
    ▼                              ▼
new AppState ◄──────────────── apply action (Stay/Pop/Push)
```

## Design Principles

**Capabilities resolve at boundaries, not in pipelines.** Views express
rendering intent via Style objects. The terminal boundary (Writer) resolves
intent against detected capability — automatically downgrading colors when
terminal color depth is limited. Don't thread detection results through
intermediate layers.

The two delivery axes:

| Axis | Mechanism | Examples | Why |
|------|-----------|----------|-----|
| Layout parameter | Explicit function arg | width, zoom | Parent allocates to children; varies per call site |
| Ambient default | ContextVar + kwarg | Palette, IconSet | Set per frame; consistent unless overridden |
| Terminal capability | Boundary resolution | Color depth | Writer resolves at output; views never branch on it |

## Layer Stack

Layers handle input routing and render ordering for modal UI.

```
┌─────────────────────┐
│   Help Layer        │  ← top: handles input first, renders last (on top)
│   state: ()         │
├─────────────────────┤
│   Search Layer      │
│   state: SearchState│
├─────────────────────┤
│   Nav Layer         │  ← base: handles if above pass, renders first
│   state: ()         │
└─────────────────────┘
```

**Input:** Top-down. Top layer handles. Returns action (Stay/Pop/Push).

**Render:** Bottom-up. Base renders, then overlays paint on top.

**Lifecycle:**
- Push: create layer with initial state, add to stack
- Stay: layer continues, state may change
- Pop: remove from stack, optionally return result

## App Loop

```python
class Surface:
    async def run(self):
        # Enter alternate screen
        # Initialize buffer

        while self._running:
            event = await self._wait_for_event()

            if event.is_resize:
                self._buf = Buffer(width, height)
                self.layout(width, height)

            elif event.is_key:
                self.on_key(event.key)

            self.render()      # state → buffer
            self._flush()      # diff → terminal

        # Exit alternate screen
```

## Component Pattern

All stateful elements follow the same pattern:

```python
# 1. State: frozen dataclass
@dataclass(frozen=True, slots=True)
class FooState:
    field: type = default

# 2. Update: pure function, returns new state
def update(state: FooState, input: T) -> FooState:
    return replace(state, field=new_value)

# 3. Render: pure function, state → Block
def render(state: FooState, context: ...) -> Block:
    return Block.text(...)
```

## Layer Pattern

Layers extend the component pattern with stack participation:

```python
@dataclass(frozen=True, slots=True)
class Layer(Generic[S]):
    name: str
    state: S
    handle: Callable[[str, S, AppState], tuple[S, AppState, Action]]
    render: Callable[[S, AppState, BufferView], None]

# Actions
Stay()              # remain active
Pop()               # remove from stack
Pop(result=value)   # remove and return result
Push(layer)         # add new layer on top
```

## Module Map

The source is organized into four subpackages plus package-root modules.
Every module is listed below. `test_architecture_invariants.py` checks this
table against the filesystem and the root tiers below, so a module that is
added, moved, or reclassified without updating the table fails the gate.

### Layer rules

The four subpackages sit in two concerns: the library (`core/`, `views/`) and
the framework (`cli/`, `tui/`). Dependencies point downward only:

| Layer | May import |
|-------|-----------|
| `core/` | stdlib, `wcwidth`, root **ambient** |
| `views/` | `core/`, root **ambient** + **foundation** |
| `tui/` | `core/`, root **ambient** + **foundation** |
| `cli/` | `core/`, root **ambient** + **foundation**; anything above only through a declared crossing seam |

`views/` never imports the framework, and `cli/` and `tui/` never import each
other or `views/` except through a seam.

### Root tiers

*Ratified 2026-10-11 (Kyle), roadmap Milestone 8.* A package-root module is not
exempt from the layer rules. Each one belongs to exactly one tier, and the tier
says both what it may import and which layers may import it:

| Tier | Imports | Imported by | Why it is at root |
|------|---------|-------------|-------------------|
| **ambient** | `core/` | every layer, `core/` included | ContextVar-carried presentation policy that `core` itself reads (palette, glyphs, ref resolution) |
| **foundation** | `core/`, ambient, foundation | every layer except `core/` | shared state primitives and delivery mechanisms used by more than one layer |
| **composite** | `core/`, `views/`, ambient, foundation, composite | entry points; `cli/` only through a seam | library entry points built on `views/` (`paint()`, diagnostics, the transcription default) |
| **framework** | anything | `cli/` only through a seam | CLI-only machinery and the package's own command-line entry points |

The rule closes the hole an unrestricted root left open. Through 0.15,
`tui/surface.py` imported `host.py`, which imported `painted.views`, so
`import painted.tui` loaded views while the tui→views ban still passed. The
frame-evidence builder (`evidence_row`/`assemble_frame`) moved to
`core/_frame.py`, which put `host.py` back in the foundation tier.
`painted.views` still re-exports both names.

### Crossing seams

A crossing is a framework-layer import that reaches a layer it may not import,
whether directly or through a composite or framework root module. Every
crossing is listed, scoped to one file:

| File | Imports | Reaches | Contract |
|------|---------|---------|----------|
| `cli/stream_surface.py` | `painted.tui.surface` | tui | alt-screen tier of the live-delivery contract (LIVE_DELIVERY_DESIGN) |
| `cli/live_meter.py` | `painted.views` | views | live frames are dressed with the public `cost_meter` |
| `cli/runner.py` | `painted._transcription` | views | transcription default renderer (RENDERER_CONTRACT_DESIGN §4) |
| `cli/prompts.py` | `painted._prompt_cell` | views | CELL prompt rung (PROMPTS_DESIGN) |

The seam table may shrink but never grow. The 2026-06-10 tripwire said that a
third legitimate seam would mean a delivery layer wants a name. Once crossings
through root modules are counted, that tripwire has already fired: all four
entries are delivery or prompt rendering that the framework orchestrates.
Extracting a delivery subsystem is the recorded follow-up. Until that happens,
a new crossing is never added to this table.

### Modules

| Subsystem | Module | Responsibility |
|-----------|--------|---------------|
| **core/** | `cell.py` | Cell, Style, Color, EMPTY_CELL |
| **core/** | `span.py` | Span, Line |
| **core/** | `block.py` | Block, Wrap |
| **core/** | `compose.py` | join_horizontal, join_vertical, join_responsive, pad, border, truncate, vslice, Align |
| **core/** | `writer.py` | Writer, ColorDepth, print_block, write_block_ansi |
| **core/** | `buffer.py` | Buffer, BufferView, CellWrite |
| **core/** | `borders.py` | BorderChars presets, current_borders(), use_borders() |
| **core/** | `html.py` | render_html(block) → str |
| **core/** | `doc.py` | doc-IR node vocabulary (Doc, Section, Def, Link, …) and doc_lens |
| **core/** | `fidelity.py` | Fidelity(depth, visible, chars, lines), Depth alias |
| **core/** | `zoom.py` | Zoom IntEnum: MINIMAL(0) SUMMARY(1) DETAILED(2) FULL(3) |
| **core/** | `renderer.py` | Renderer — the `(data, fidelity, width) → Block` contract as a type |
| **core/** | `errors.py` | PaintedError, DeclarationError, ContractError, LifecycleError |
| **core/** | `_frame.py` | evidence_row, assemble_frame — law-6 scroll evidence (public via `painted.views`) |
| **core/** | `_text_width.py` | display_width, char_width, truncate, truncate_ellipsis |
| **core/** | `_row_ops.py` | wide-character-safe row traversal |
| **core/** | `_normalize.py` | sequence-field normalization for frozen primitives |
| **core/** | `_color.py` | shared color conversions |
| **views/** | `record.py` | record_line, record_timeline, PayloadLens, GutterFn, gutter_lifecycle, etc. |
| **views/** | `big_text.py` | render_big(), BigTextFormat |
| **views/** | `_traceback.py` | render_traceback — an exception as a record tree |
| **views/** | `_profile.py` | profile(), parse_collapsed(), ProfileResult |
| **views/lens/** | `table.py` | table_lens(data, zoom, width) → Block |
| **views/lens/** | `tree.py` | tree_lens(data, zoom, width) → Block |
| **views/lens/** | `chart.py` | chart_lens(data, zoom, width) → Block |
| **views/lens/** | `flame.py` | flame_lens(data, zoom, width, ...) → Block |
| **views/lens/** | `shape.py` | shape_lens(content, zoom, width) → Block (auto-dispatch), transcribe |
| **views/lens/** | `_records.py` | declared-schema vocabulary shared by record-reading lenses |
| **views/components/** | `_list_view.py` | ListState, list_view() |
| **views/components/** | `_table.py` | Column, TableState, table() |
| **views/components/** | `_data_explorer.py` | DataNode, DataExplorerState, data_explorer() |
| **views/components/** | `_text_input.py` | TextInputState, text_input() |
| **views/components/** | `_spinner.py` | SpinnerState, spinner() |
| **views/components/** | `progress.py` | ProgressState, progress_bar() |
| **views/components/** | `_sparkline.py` | sparkline(), sparkline_with_range() |
| **views/components/** | `_meter.py` | cost_meter() |
| **views/components/** | `_callout.py` | callout(), Severity |
| **views/components/** | `_line_ellipsis.py` | styled-Line ellipsis truncation (law-6 row-tail mark) |
| **cli/** | `runner.py` | CliRunner, run_cli |
| **cli/** | `types.py` | Tag, OutputMode, Format, CliContext, detect_context, add_cli_args, parse_fidelity |
| **cli/** | `app_runner.py` | AppCommand, AppRunner, run_app |
| **cli/** | `help.py` | HelpArg, help_doc — help as a doc-IR document |
| **cli/** | `prompts.py` | Prompt[T], Confirm, Select, Input, PromptSession |
| **cli/** | `_prompt_line.py` | LINE prompt rung (cooked mode) |
| **cli/** | `complete.py` | shell completion — the parser's third reflection |
| **cli/** | `completion_shell.py` | shell transport for completion |
| **cli/** | `_argwalk.py` | shared walk over an argparse parser's actions |
| **cli/** | `stream_surface.py` | StreamSurface — alt-screen delivery for sustained streams |
| **cli/** | `live_meter.py` | LiveMeter — delivery-cost gauge for live frames |
| **tui/** | `surface.py` | Surface (base class), HostSurface, Emit, LifecycleHook |
| **tui/** | `layer.py` | Layer, Stay, Pop, Push, Quit, process_key, render_layers |
| **tui/** | `region.py` | Region |
| **tui/** | `testing.py` | TestSurface, CapturedFrame |
| **root · ambient** | `palette.py` | Palette, current_palette(), use_palette(), DEFAULT/NORD/MONO/PAINTED_PALETTE |
| **root · ambient** | `icon_set.py` | IconSet, current_icons(), use_icons(), ASCII_ICONS |
| **root · ambient** | `refs.py` | RefScheme, use_refs(), resolve_ref() |
| **root · foundation** | `capabilities.py` | Capabilities, current_capabilities(), use_capabilities() |
| **root · foundation** | `vocabulary.py` | Vocabulary, Thresholds, mark_style — the mark channel |
| **root · foundation** | `theme.py` | Theme, use_theme(), DEFAULT/NORD/MONO/PAINTED_THEME |
| **root · foundation** | `viewport.py` | Viewport |
| **root · foundation** | `cursor.py` | Cursor — bounded index state |
| **root · foundation** | `focus.py` | Focus, ring_next, ring_prev |
| **root · foundation** | `search.py` | Search, filter_contains, filter_prefix, filter_fuzzy |
| **root · foundation** | `keyboard.py` | KeyboardInput, cbreak_supported, read_key |
| **root · foundation** | `mouse.py` | MouseEvent, MouseButton, MouseAction, parse_sgr_mouse |
| **root · foundation** | `inplace.py` | InPlaceRenderer |
| **root · foundation** | `host.py` | ViewportAdapter, HostViewport, HostEvent — the host rung's viewport adapter |
| **root · foundation** | `publish.py` | to_html — the doc-IR publisher |
| **root · foundation** | `_sparkline_core.py` | sparkline implementation shared by views |
| **root · foundation** | `_timer.py` | FrameTimer — per-phase render-loop timing |
| **root · composite** | `display.py` | paint() |
| **root · composite** | `diagnostics.py` | PaintedHandler, install, DEFAULT_THRESHOLDS |
| **root · composite** | `_transcription.py` | transcription_renderer — run_cli's default renderer |
| **root · framework** | `__init__.py` | the package facade (lazy re-exports, including `painted.cli`) |
| **root · framework** | `__main__.py` | `python -m painted` |
| **root · framework** | `_prompt_cell.py` | CELL prompt rung (raw mode) |
| **root · framework** | `_docs_cli.py` | `painted docs` |
| **root · framework** | `_doc_pages.py` | authored doc-IR pages behind `painted docs` and the site |
| **root · framework** | `_demo_cli.py` | `painted demos` |
| **root · framework** | `_demo_discovery.py` | render-free demo discovery |

## Quick Reference

| Primitive | Purpose | Pattern |
|-----------|---------|---------|
| Cell/Style | Atomic styled character | Immutable value |
| Span/Line | Styled text | Immutable value |
| Block | Rectangle of cells | Immutable, composable |
| Buffer | 2D canvas + diff | Mutable (paint target) |
| BufferView | Clipped region | Mutable (delegates to Buffer) |
| Component | Stateful widget | State dataclass + pure functions |
| Layer | Modal input scope | State + handle + render + stack |
| Surface | Main loop | Owns state, orchestrates flow |
