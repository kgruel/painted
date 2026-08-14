# painted.core — the renderer's foundation

The bottom of the stack: Cell, Style, Span, Line, Block, compose, the doc-IR,
Buffer, Writer, and the `Fidelity`/`Renderer` vocabulary. Pure library — turns
data into terminal cells, knows nothing of argv, modes, or dispatch.

Contributor-facing, a standalone file (no README symlink — that convention is
only for the consumer guides `src/painted/{,views,tui}`), like `tests/` and
`demos/`. **Don't restate the maps that already exist:** root `CLAUDE.md` (Level
1) names every module and responsibility, `docs/ARCHITECTURE.md` has the stack +
data flow, `docs/PRIMITIVES.md` is the consumer API reference, and
`src/painted/CLAUDE.md` (Level 1) is the *usage* guide. This file is the
internal invariants you need when **modifying** a primitive — the cross-cutting
rules that live in no single module because they're emergent across the cluster.

The modules themselves carry rich design docstrings (`block.py`'s wrap-engine
note, `doc.py`'s whole-module rationale, `cell.py`'s `scrub_control`,
`renderer.py`). Read the one you're editing first — this page maps *which*
invariant bites *where*, so you know what to read before you touch it.

---

## Level 0 — The boundary

**Trigger**: I'm about to add or move code in `core/`.

- **Self-contained.** `core/` may import stdlib, `wcwidth`, and a few root
  modules it depends on (`palette`, `icon_set`, `refs`) — but never `views/`,
  `cli/`, or `tui/`. Gated by `test_core_is_self_contained`
  (`tests/unit/test_architecture_invariants.py`). A cross-layer need means the
  code belongs one layer up, not a new import here.
- **Frozen everything.** `Style`, `Cell`, `Span`, `Line` are frozen dataclasses;
  `Block` is hand-frozen (`__slots__` + a `_frozen` guard in `__setattr__`).
  Construct new, never mutate. `Buffer`/`BufferView` are the deliberate mutable
  exception — the paint *target*, not a value.

---

## Level 1 — The invariants that bite

**Trigger**: I'm changing how cells, blocks, wrapping, or refs are built.

| Invariant | Where it lives | The footgun |
|-----------|----------------|-------------|
| **`Block()` vs `Block._create`** | `block.py` | `Block()` validates row widths + freezes rows. `Block._create` is the fast path that does **neither** — rows must already be frozen tuples of *exactly* `width`. Use it only when you built the rows and know they're correct; a wrong width is silent corruption, not an error. |
| **The ref lane** | `block.py`, `span.py`, `buffer.py`, `compose.py` | Denotation (`ref`) rides a *parallel grid*: `_refs` is `None` in the common case (zero allocation) or a full same-dimensions grid. Every cell-building path must produce a parallel ref lane **or** `None` — never a ragged one. Refs survive wrap, compose, and paint (a reflowed link keeps its ref on every fragment). See `docs/REFS_DESIGN.md`. |
| **One wrap engine** | `block.py` (`--- Styled wrap engine ---`) | Wrapping *and materialization* operate on a *styled-run stream* (`_StyledRuns` — one `(text, Style, ref)` run per uniformly styled stretch, the `Span` shape); `_cells_from_text` is the per-run core, batching through the cached cell maps. A single-style `str` is the degenerate one-run case — there is no parallel str/styled logic to keep in sync; don't add one. (`Block.text`'s single-line-ASCII `Wrap.NONE` branch inlines `_ascii_row_tuple` — the degenerate case kept branch-local for the hottest constructor, not a second engine.) |
| **Cell/style caches** | `block.py`, `cell.py`, `_row_ops.py`, `compose.py` | `_style_cell_maps`, `_merge_cache`, `_space_cells`, `_border_cell_cache`, `_row_ops.blank_cell` cache Cells keyed by frozen `Style`. They're why `Style` must stay hashable/frozen. Reuse the cache accessors rather than constructing `Cell(" ", style)` inline on hot paths. |
| **Control-char scrubbing** | `cell.py` (`scrub_control`) | C0/C1 controls are neutralized to spaces at `Cell.__post_init__` — a single source of truth (the LINE prompt writer mirrors it for its string path). A raw ESC/TAB in a display cell corrupts the grid and breaks the width contract. Never assemble display text that bypasses `Cell`. |
| **Width is display columns** | `_text_width.py` (wcwidth) | A block's width is its *display* width, never `len()`: wide chars count 2, combining marks 0. A passed `width` is exact (clip/pad, or reflow with `Wrap`). See the width-contract fragment in `docs/PRIMITIVES.md`. |

---

## Level 2 — Why `fidelity.py` and `renderer.py` live here

**Trigger**: I'm touching the disclosure/renderer vocabulary.

`core/` also holds the two *specs* the CLI framework compiles into — but not the
grammar that compiles them (that's `cli/`). This is the deliberate split: the
spec sits in `core`, the argv grammar that produces it sits in `cli`.

- **`fidelity.py`** — `Fidelity(depth, visible, chars, lines)`, the compiled
  disclosure spec (`docs/FIDELITY_DESIGN.md`). The flag grammar (`Tag`,
  `parse_fidelity`) lives in `cli/` and compiles *into* this.
- **`renderer.py`** — `Renderer`, the `(data, fidelity, width) → Block` contract
  as a type alias (`docs/RENDERER_CONTRACT_DESIGN.md`). Core placement is load-
  bearing: the 0.13 host rung runs the same renderer through `Surface`, and
  `tui/` imports nothing from `cli/`. `Block`/`Fidelity` are forward refs so the
  alias costs no runtime imports — `core.renderer` stays stdlib-only.

---

## Internal module map

The public-surface modules are in the maps cited above. These are the private /
structural pieces a contributor meets inside `core/`:

| Module | Role |
|--------|------|
| `_row_ops.py` | Row traversal over wide-char encoding (`blank_cell`, span iteration) — shared by `block.py`/`writer.py` |
| `_text_width.py` | `display_width`, `char_width`, `truncate*` — the wcwidth boundary |
| `_color.py` | RGB→256/16 down-conversion helpers for the Writer |
| `doc.py` | The doc-IR node vocabulary + `doc_lens`; a *document* compositor, peer of `compose.py` (read its module docstring — the `eff` tier cascade is subtle) |
| `html.py` | `render_html(block)` — the ANSI-parallel HTML sink |
| `errors.py` | `ContractError` etc. — raised at construction seams here |

## Adding to core

`./dev check` runs the arch tier first (structure before behavior). A new public
export on `painted.core` is a semver-MAJOR event — add it to the
`test_public_api.py` snapshot deliberately (the diff is the review). A new frozen
state type is checked by the arch tier too.
