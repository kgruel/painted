# painted Architecture

Data-flow reference for the painted TUI framework.

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

The source is organized into four subsystems. Layer boundaries are enforced by architecture tests: `core/` is self-contained; `views/`, `cli/`, and `tui/` each import only from `core/` and root-level modules.

| Subsystem | Module | Responsibility |
|-----------|--------|---------------|
| **core/** | `cell.py` | Cell, Style, Color, EMPTY_CELL |
| **core/** | `span.py` | Span, Line |
| **core/** | `block.py` | Block, Wrap |
| **core/** | `compose.py` | join_horizontal, join_vertical, join_responsive, pad, border, truncate, vslice, Align |
| **core/** | `writer.py` | Writer, ColorDepth, print_block, write_block_ansi |
| **core/** | `fidelity.py` | Fidelity(depth, visible, chars, lines), Depth alias |
| **core/** | `zoom.py` | Zoom IntEnum: MINIMAL(0) SUMMARY(1) DETAILED(2) FULL(3) |
| **core/** | `buffer.py` | Buffer, BufferView, CellWrite |
| **core/** | `borders.py` | BorderChars presets, current_borders(), use_borders() |
| **core/** | `html.py` | render_html(block) → str |
| **core/** | `_text_width.py` | display_width, char_width, truncate, truncate_ellipsis |
| **cli/** | `runner.py` | CliRunner, run_cli |
| **cli/** | `types.py` | OutputMode, Format, CliContext, resolve_mode, detect_context, add_cli_args, parse_* |
| **cli/** | `app_runner.py` | AppCommand, AppRunner, run_app |
| **cli/** | `help.py` | HelpFlag, HelpGroup, HelpData, HelpArg, render_help, build_help_data |
| **views/** | `record.py` | record_line, record_timeline, PayloadLens, GutterFn, gutter_lifecycle, etc. |
| **views/lens/** | `chart.py` | chart_lens(data, zoom, width) → Block |
| **views/lens/** | `flame.py` | flame_lens(data, zoom, width, ...) → Block |
| **views/lens/** | `shape.py` | shape_lens(content, zoom, width) → Block (auto-dispatch) |
| **views/lens/** | `tree.py` | tree_lens(data, zoom, width) → Block |
| **views/components/** | `list_view.py` | ListState, list_view() |
| **views/components/** | `table.py` | Column, TableState, table() |
| **views/components/** | `spinner.py` | SpinnerState, spinner() |
| **views/components/** | `progress.py` | ProgressState, progress_bar() |
| **views/components/** | `sparkline.py` | sparkline(), sparkline_with_range() |
| **views/components/** | `text_input.py` | TextInputState, text_input() |
| **views/components/** | `data_explorer.py` | DataNode, DataExplorerState, data_explorer() |
| **views/** | `profile.py` | profile(), parse_collapsed(), ProfileResult |
| **views/** | `big_text.py` | render_big(), BigTextFormat |
| **tui/** | `surface.py` | Surface (base class), Emit, LifecycleHook |
| **tui/** | `layer.py` | Layer, Stay, Pop, Push, Quit, process_key, render_layers |
| **tui/** | `keyboard.py` | KeyboardInput, Input |
| **tui/** | `mouse.py` | MouseEvent, MouseButton, MouseAction, parse_sgr_mouse |
| **tui/** | `region.py` | Region |
| **tui/** | `testing.py` | TestSurface, CapturedFrame |
| **root** | `palette.py` | Palette, current_palette(), use_palette(), DEFAULT_PALETTE, NORD_PALETTE, MONO_PALETTE |
| **root** | `icon_set.py` | IconSet, current_icons(), use_icons(), ASCII_ICONS |
| **root** | `theme.py` | Theme, use_theme(), DEFAULT_THEME, NORD_THEME, MONO_THEME |
| **root** | `inplace.py` | InPlaceRenderer |
| **root** | `viewport.py` | Viewport |
| **root** | `display.py` | show() |
| **root** | `focus.py` | Focus, ring_next, ring_prev |
| **root** | `search.py` | Search, filter_contains, filter_prefix, filter_fuzzy |

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
