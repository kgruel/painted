# Primitives Reference

Quick reference for painted primitives. See ARCHITECTURE.md for data flow, DATA_PATTERNS.md for patterns.

---

## Cell / Style

**Style** — Immutable text attributes (fg, bg, bold, italic, underline, reverse, dim).

```python
style = Style(fg="cyan", bold=True)
merged = base_style.merge(overlay_style)  # overlay wins non-None
```

**Cell** — Single character + style. Atomic unit.

```python
cell = Cell("x", style)
# Cells are the leaf data; you rarely create them directly
```

**Connects to:** Buffer stores Cells. Block contains rows of Cells.

---

## Buffer / BufferView

**Buffer** — Mutable 2D grid of Cells with diff support.

| Method | Description |
|--------|-------------|
| `put(x, y, char, style)` | Set single cell |
| `put_text(x, y, text, style)` | Write string (wide-char aware) |
| `fill(x, y, w, h, char, style)` | Fill rectangle |
| `region(x, y, w, h)` | Get clipped BufferView |
| `diff(other)` | List of changed CellWrites |
| `clone()` | Deep copy for diffing |

```python
buf = Buffer(80, 24)
buf.put_text(0, 0, "Hello", Style(fg="green"))
changes = new_buf.diff(old_buf)  # only what changed
```

**BufferView** — Clipped, translated window into a Buffer. Same API as Buffer for put/put_text/fill.

```python
view = buf.region(10, 5, 40, 10)  # x=10, y=5, 40x10
view.put(0, 0, "X", style)        # writes to buf[10,5]
```

**Connects to:** Surface owns Buffer. Blocks paint to Buffer/BufferView. Layers receive BufferView.

---

## Block

**Block** — Immutable rectangle of Cells with known dimensions.

| Method | Description |
|--------|-------------|
| `Block.text(s, style, width=, wrap=)` | Create from string |
| `Block.empty(w, h, style=)` | Space-filled block |
| `paint(buffer, x, y)` | Transfer cells to buffer |
| `row(y)` | Access row by index |

```python
block = Block.text("Status: OK", Style(fg="green"), width=20)
block.paint(buf, 5, 3)
```

**Wrap modes:** `Wrap.NONE`, `Wrap.CHAR`, `Wrap.WORD`, `Wrap.ELLIPSIS`

**Width contract** — a Block's `width` is **exact**. Pass `width=N` and the result is exactly `N` columns: shorter content is padded, longer content reflows to more rows; it never overflows horizontally. Omit `width` and the block sizes to its content (natural). Two distinct guarantees both hold and are easy to conflate: *width-aware* = wcwidth counts display columns (so `width != len()` for emoji/CJK); *honors width* = the output's width equals the width you requested. Exactness is what lets composition carve a budget (`60 + gutter + 60 = 124`) and trust the pieces tile with no gap or overflow, at any terminal size. `fit_to_width(block, w)` is the block-level realization (truncate if wide, pad if narrow).

**Connects to:** Composed via `join_horizontal`, `join_vertical`, `pad`, `border`, `truncate`, `fit_to_width`. Paints to Buffer/BufferView.

---

## Span / Line

**Span** — Text run with single style. Immutable.

```python
span = Span("error", Style(fg="red", bold=True))
print(span.width)  # display width (wide-char aware)
```

**Line** — Sequence of Spans forming one line.

| Method | Description |
|--------|-------------|
| `Line.plain(text, style)` | Single-span line |
| `paint(view, x, y)` | Render to BufferView |
| `truncate(max_width)` | Return truncated Line |
| `to_block(width)` | Convert to Block |

```python
line = Line((Span("Name: "), Span("Alice", Style(bold=True))))
line.paint(view, 0, 0)
```

**Connects to:** Can convert to Block via `to_block()`. Paints directly to BufferView.

---

## Layer

**Layer** — Bundles state + handle + render for modal stacking.

```python
@dataclass(frozen=True, slots=True)
class Layer(Generic[S]):
    name: str
    state: S
    handle: Callable[[str, S, AppState], tuple[S, AppState, Action]]
    render: Callable[[S, AppState, BufferView], None]
```

**Actions:** `Stay()`, `Pop(result=)`, `Push(layer)`, `Quit()`

| Function | Description |
|----------|-------------|
| `process_key(key, state, get_layers, set_layers)` | Route key through stack |
| `render_layers(state, buf, get_layers)` | Render bottom-to-top |

```python
def handle(key, state, app):
    if key == "q":
        return state, app, Pop()
    return replace(state, query=state.query + key), app, Stay()

search_layer = Layer("search", SearchState(), handle, render)
```

**Connects to:** Surface uses process_key/render_layers. Layers contain their own state, receive app state.

---

## Focus

**Focus** — Two-tier focus state (navigation vs captured).

| Method | Description |
|--------|-------------|
| `focus(id)` | Move focus to id, release capture |
| `capture()` | Widget takes keyboard |
| `release()` | Return to navigation |
| `toggle_capture()` | Toggle capture state |

```python
focus = Focus(id="sidebar")
focus = focus.capture()      # sidebar has keyboard
focus = focus.focus("main")  # move to main, released
```

**Navigation functions:** `ring_next`, `ring_prev`, `linear_next`, `linear_prev`

```python
items = ("sidebar", "main", "footer")
next_id = ring_next(items, focus.id)  # wraps around
```

**Connects to:** Lives in app state. Checked by components to style/behavior.

---

## Search

**Search** — Filtered selection state: query + selected index.

| Method | Description |
|--------|-------------|
| `type(char)` | Append to query, reset selection |
| `backspace()` | Remove last char |
| `clear()` | Empty query |
| `select_next(count)` | Move selection down (wrapping) |
| `select_prev(count)` | Move selection up (wrapping) |
| `selected_item(matches)` | Get current selection |

```python
search = Search()
search = search.type("f").type("o")  # query="fo"
matches = filter_contains(items, search.query)
search = search.select_next(len(matches))
item = search.selected_item(matches)
```

**Filter functions:** `filter_contains`, `filter_prefix`, `filter_fuzzy`

**Connects to:** Used by search layers. Filter functions are standalone utilities.

---

## Lens Functions

Four built-in strategies. Lenses are plain functions `(data, zoom, width) -> Block`. All are importable from `painted.views`.

- **shape_lens** — Auto-dispatches by data shape. Numeric sequences → chart_lens. Hierarchical dicts → tree_lens. Everything else uses built-in shape rendering (zoom 0: type/count, zoom 1: summary, zoom 2: full).
- **tree_lens** — Hierarchical data with branch characters. Supports dicts, tuples, node protocol.
- **chart_lens** — Numeric data as sparklines (zoom 1) or bar charts (zoom 2).
- **flame_lens** — Proportional width visualization. Nested dicts → flame graph rows.

```python
from painted.views import shape_lens, tree_lens, chart_lens, flame_lens

block = shape_lens({"name": "Alice", "age": 30}, zoom=1, width=40)  # keys
block = shape_lens([10, 20, 30], zoom=1, width=40)                  # sparkline
block = tree_lens({"src": {"main.py": None}}, zoom=2, width=40)     # tree
block = chart_lens({"cpu": 70, "mem": 50}, zoom=2, width=40)        # bars
block = flame_lens(profile_dict, zoom=2, width=80)                  # flame graph
```

**Sparklines** — stateless inline mini-charts, distinct from chart_lens:

```python
from painted.views import sparkline, sparkline_with_range

block = sparkline([12, 15, 23, 45, 67], width=20)
block = sparkline_with_range([12, 15, 23, 45, 67], width=20, min_val=0, max_val=100)
```

**Connects to:** Produces Blocks. Nested structures reduce zoom at each level. Source modules: `views/lens/chart.py`, `views/lens/flame.py`, `views/lens/shape.py`, `views/lens/tree.py`, `views/components/_sparkline.py`.

---

## Components

Stateful view elements. Pattern: frozen `State` dataclass + pure `render_fn(state, ...) → Block`. All importable from `painted.views`.

| Import | State | Purpose |
|--------|-------|---------|
| `spinner, SpinnerState` | `SpinnerState(frame)` | Animated spinner |
| `progress_bar, ProgressState` | `ProgressState(value, total)` | Horizontal progress bar |
| `list_view, ListState` | `ListState(cursor, viewport)` — `.selected` property | Scrollable list with selection |
| `table, TableState, Column` | `TableState(cursor, viewport)` — `.selected_row` property | Scrollable table with headers |
| `text_input, TextInputState` | `TextInputState(text, cursor, scroll_offset)` | Single-line input with cursor |
| `data_explorer, DataExplorerState` | `DataExplorerState(...)` | Interactive data browser for nested structures |

```python
from painted.views import spinner, SpinnerState, DOTS
from painted.views import progress_bar, ProgressState
from painted.views import data_explorer, DataExplorerState

state = SpinnerState(frames=DOTS, frame=0)
block = spinner(state)

state = ProgressState(value=0.42)  # 0.0-1.0
block = progress_bar(state, width=40)
```

State is owned by the caller. Update with `dataclasses.replace()`.

**Visual effects:**

```python
from painted.views import render_big, BigTextFormat

block = render_big("OK", style=Style(fg="green"))
block = render_big("DONE", fmt=BigTextFormat.OUTLINE)
```

Source modules: `views/components/`, `views/big_text.py`.

---

## Composition Functions

Not a primitive, but essential for combining Blocks.

| Function | Description |
|----------|-------------|
| `join_horizontal(*blocks, gap=, align=)` | Left-to-right |
| `join_vertical(*blocks, align=)` | Top-to-bottom |
| `join_responsive(*blocks, available_width, gap=)` | Horizontal if blocks fit in available_width, else vertical |
| `pad(block, left=, right=, top=, bottom=)` | Add spacing |
| `border(block, chars=, style=, title=)` | Wrap with border |
| `truncate(block, width)` | Clip with ellipsis |
| `vslice(block, offset, visible)` | Vertical slice for scrolling |

```python
panel = border(pad(content, left=1, right=1), title="Info")
layout = join_horizontal(sidebar, main, gap=1)
```

**Align:** `Align.START`, `Align.CENTER`, `Align.END`

All composition functions are importable directly from `painted`.
