# painted.views — Data Rendering

Lenses (stateless) and components (frozen state + pure render). Import everything from here.

## Lenses

Stateless functions: `fn(data, zoom, width) → Block`.

```python
from painted.views import shape_lens, tree_lens, chart_lens, flame_lens, sparkline
```

- **`shape_lens`** — auto-dispatch by data shape: the explicit *inference* lens (`lens=shape_lens`). Dict → key-value, list → items, numeric → chart, nested → tree. `paint()`'s no-lens default is `transcribe` — it never infers arrangement; `shape_lens` is what you reach for when you want the guess.
- **`tree_lens`** — hierarchical data with expand/collapse.
- **`chart_lens`** — numeric data as horizontal bar charts.
- **`flame_lens`** — proportional visualization (flame graph style).
- **`sparkline`** / **`sparkline_with_range`** — inline mini-charts from numeric sequences.
- **`cost_meter`** — one-row gauge of observed per-frame costs against a time budget; returns `None` when there are no observations, so static output stays undressed.
- **`callout`** — severity-tagged message line (`callout(subject, *, severity, detail, hint, box, width)`); `severity` is a `Severity` enum driving glyph + color, with optional muted detail / `↳ hint` lines and an optional box (width-exact, border included).
- **`render_traceback`** — an exception as a record tree: `render_traceback(exc, zoom, width, *, suppress=(), redact=default_redact) → Block`. Accepts a live `BaseException` (captured internally) or a pre-captured `TracebackException`. Frames are records on a continuous gutter rail (the rail encodes ONE dimension — frame origin: app vs suppressed/library); cause/context chains and `ExceptionGroup`s are the tree. The zoom ladder is additive: MINIMAL (type + message + innermost frame) → SUMMARY (frame stack, chains summarized, suppressed folded) → DETAILED (source ±1 with a display-column-correct caret, chains fully rendered) → FULL (source ±3, redacted + budgeted locals, groups expanded). `suppress` folds frames whose module path matches a substring; `redact` masks sensitive local names at FULL. This is the renderer `painted.install()` and `PaintedHandler` deliver — see the API guide's Diagnostics section and `docs/DIAGNOSTICS_DESIGN.md`.
- **`NodeRenderer`** — callback protocol for custom tree node rendering.

## Components

Frozen state + pure render function. Pattern: `State + render_fn(state, ...) → Block`.

```python
from painted.views import SpinnerState, spinner, DOTS
from painted.views import ProgressState, progress_bar
from painted.views import ListState, list_view
from painted.views import TableState, Column, table
from painted.views import TextInputState, text_input
from painted.views import DataExplorerState, data_explorer
```

- **`spinner(state) → Block`** — animated spinner. Frames: `DOTS`, `LINE`, `BRAILLE`.
- **`progress_bar(state) → Block`** — horizontal progress bar.
- **`list_view(state, items, render_item) → Block`** — scrollable list with selection.
- **`table(state, rows, columns) → Block`** — scrollable table with headers.
- **`text_input(state) → Block`** — single-line input with cursor.
- **`data_explorer(state) → Block`** — interactive data browser.

<!-- docgen:begin frag:frozen-state#full -->
All state types are frozen — immutable dataclasses. State is created through its
constructor and updated with `dataclasses.replace()`, which returns *new* state; it is
never mutated in place. Rendering is a pure function of that state —
`render_fn(state, ...) → Block`: same inputs, same output, no side effects.
<!-- docgen:end -->

## Aesthetic

Contextual defaults via ContextVar — set globally or scoped via context manager.

```python
from painted.views import Palette, use_palette, current_palette, DEFAULT_PALETTE, NORD_PALETTE, MONO_PALETTE, PAINTED_PALETTE
from painted.views import IconSet, use_icons, current_icons, ASCII_ICONS
```

- **`Palette`** — 5 semantic Style roles (`success`, `warning`, `error`, `accent`, `muted`), plus a `series` categorical ramp (consumed by `flame_lens`).
- **`IconSet`** — named glyph slots: spinner, progress, tree, sparkline.
- `use_palette()` / `use_icons()` — setter (no arg = get current) or context manager (scoped override).

## Visual effects

```python
from painted.views import render_big, BigTextFormat, BIG_GLYPHS
```

`render_big(text, style)` — large block-character text.

## Profile bridge

```python
from painted.views import profile, parse_collapsed, ProfileResult
```

Flamegraph-compatible profiling utilities.
