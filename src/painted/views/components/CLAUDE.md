# painted._components — Internal Implementation

**Import from `painted.views`, not here.** This is the internal implementation of stateful view components.

## Pattern

<!-- docgen:begin frag:frozen-state#full -->
All state types are frozen — immutable dataclasses. State is created through its
constructor and updated with `dataclasses.replace()`, which returns *new* state; it is
never mutated in place. Rendering is a pure function of that state —
`render_fn(state, ...) → Block`: same inputs, same output, no side effects.
<!-- docgen:end -->

## File Map

| File | State | Render | Purpose |
|------|-------|--------|---------|
| `_spinner.py` | `SpinnerState` | `spinner()` | Animated spinner (DOTS, LINE, BRAILLE frames) |
| `progress.py` | `ProgressState` | `progress_bar()` | Horizontal progress bar |
| `_list_view.py` | `ListState` | `list_view()` | Scrollable list with selection |
| `_text_input.py` | `TextInputState` | `text_input()` | Single-line input with cursor |
| `_table.py` | `TableState` | `table()` | Scrollable table with Column headers |
| `_sparkline.py` | — | `sparkline()` | Inline mini-chart (stateless) |
| `_meter.py` | — | `cost_meter()` | Frame-cost gauge vs a budget (stateless) |
| `_callout.py` | — | `callout()` | Severity-tagged message line / panel (stateless) |
| `_data_explorer.py` | `DataExplorerState` | `data_explorer()` | Interactive data browser |

Backing files are underscore-private (`_name.py`) wherever the public name would
otherwise equal the filename — this keeps the re-exported surface and the file
namespace disjoint so a submodule import can never shadow a public function (the
`profile`/`profile.py` collision class, review #1). Enforced by
`test_public_names_do_not_shadow_submodules`. `progress.py` keeps its name —
its public export is `progress_bar`, which doesn't collide.

## Public API

All exports are re-exported through `painted.views`. Consumers should never import
from these submodules directly — the underscore prefix signals this is internal.
