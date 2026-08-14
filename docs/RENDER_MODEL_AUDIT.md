# Render-model law audit — full evidence record

**Audited: 2026-07-10 at commit `10d7fef`.** Companion to
`docs/RENDER_MODEL.md` §8 (which carries the compressed verdicts); this
file preserves the full tables so the inventory is reproducible and
diffable against future states of the code. Method: four parallel tracers
(one Opus on law 6, three Sonnet on laws 4, 8, and 1+7), each returning
file:line-cited findings; cross-reviewed by GPT-5.6, which caught one
classification error (law 7, corrected below and marked).

**Law 6 disposition updated 2026-07-18 (0.14 honesty-remediation, S1–S5).**
The 25-path law-6 inventory below is the 2026-07-10 finding; its *descriptive*
columns (trigger / content lost / evidence / class) are preserved verbatim as
the reproducible record. The **verdict** and **test pin** columns are updated
to current status: each remediated path now MARKS (its slice + evidence pin
named), and each path in the ruled silent-cut exempt set (store decision
`design/honesty-remediation-scope`, Kyle 2026-07-18) is classed EXEMPT and
pinned by the shrink-only ratchet
(`tests/unit/test_architecture_invariants.py::test_law6_silent_exemptions_are_real_and_shrink_only`).
The milestone closed the open silent paths the 2026-07-10 audit found; what
stays silent is the ruled mechanism/selection set, not an unaddressed gap.

## Law 6 — geometry-driven loss inventory (25 paths)

Headline (2026-07-10): the marked/silent split tracks the **layer**, not the
axis. Width loss in the lens/compose layer is almost always marked; the same
loss in the primitive constructors and **all height loss** is silent.
No height-overflow evidence primitive and no rendered scroll affordance
exists anywhere in `src/painted/` (zero matches for scrollbar / "more
above/below" / arrows in src or tests).

*Updated 2026-07-18 (0.14 S1–S5): height-overflow evidence now exists — the
shared `evidence_row`/`assemble_frame` reserve a "N more rows" row for the
windowed components and the host viewport (HOST_RUNG_DESIGN §6). The
allocation-driven deciders across both axes mark; what stays silent is the
ruled layer of mechanisms and defaults (see the disposition note in the
header). The verdict/pin columns below carry the per-path status.*

| # | file:line | trigger | content lost | evidence | class | verdict | test pin |
|---|-----------|---------|--------------|----------|-------|---------|----------|
| 1 | `core/block.py:306-401` (`Block.paint`) | block taller/wider than target `Buffer`/`BufferView` | every row ≥ `buffer.height`, every col ≥ `buffer.width` | NOTHING (docstring: "Clips to buffer bounds") | allocation (height + width) | **EXEMPT** (ruled: paint mechanism, §4 ownership) | `test_law6_silent_exemptions_are_real_and_shrink_only` (+ `test_block_extended.py:235,258` clip mechanics) |
| 2 | `core/buffer.py:62-70,335-337` (`put`/`BufferView.put`) | out-of-bounds cell write | the cell | NOTHING ("silently ignored") | allocation (both axes) | **EXEMPT** (ruled: paint mechanism, §4 ownership) | `test_law6_silent_exemptions_are_real_and_shrink_only` (+ `test_buffer_extended.py:22,32` silence intended) |
| 3 | `tui/surface.py:98,239` + `_flush` | rendered frame exceeds terminal; buffer sized to terminal | off-screen rows/cols (via #1) | NOTHING | allocation (height + width) | **EXEMPT by delegation to #1/#2** — *not a separate ruled identity*. The raw `Surface` paint that loses off-screen cells IS ruled mechanisms #1/#2 (`Block.paint`/`Buffer.put`) acting at the delivery target, so it inherits their exemption; it is not itself in the ruled set. Distinctly, a host *viewporting* natural-height content is a decider that owns the loss and draws the `evidence_row` "N more rows" (`ViewportAdapter`, HOST_RUNG_DESIGN §6, 0.13). | ratchet pins the underlying identities #1/#2 only (`test_law6_silent_exemptions_are_real_and_shrink_only` lists `Block.paint`/`Buffer.put`, *not* Surface); host-viewport evidence: `test_host_adapter.py::TestResizeMatrix::test_any_height_change_recomposes_the_frame` |
| 4 | `views/components/_list_view.py:110-155` | `len(items) > visible_height` | items outside `[offset, offset+visible)` | NOTHING — `Viewport.can_scroll` computed, never rendered | allocation (height) | **MARKED (0.14 S1)** — reserved evidence row via `evidence_row`/`frame_capacity` | `TestLaw6EvidencePins::test_list_view_overflow_marks_and_fit_is_clean` |
| 5 | `views/components/_table.py:492-534` | `len(rows) > visible_height` | rows outside window | NOTHING (same as #4) | allocation (height) | **MARKED (0.14 S1)** — reserved evidence row (body window) | `TestLaw6EvidencePins::test_table_overflow_marks_and_fit_is_clean` |
| 6 | `views/components/_list_view.py:139` (`row_line.truncate`) | item Line wider than `max_width` | tail of the row | NOTHING | visual clipping | **MARKED (0.14 S1)** — row-tail ellipsis (the component owns the cut), width-1 waiver | `TestLaw6EvidencePins::test_list_view_row_tail_ellipsis_marks_and_fits_clean` |
| 7 | `core/span.py:60-84` (`Line.truncate`) | Line wider than `max_width` | tail spans/chars | NOTHING | visual clipping | **EXEMPT** (ruled: primitive; the caller that chose the width owes the mark) | `test_law6_silent_exemptions_are_real_and_shrink_only` (+ `test_span.py` width) |
| 8 | `core/span.py:105-150` (`Line.to_block`) | Line wider than `width` | tail | NOTHING | visual clipping | **EXEMPT** (ruled: primitive; same ownership split as `Line.truncate`) | `test_law6_silent_exemptions_are_real_and_shrink_only` |
| 9 | `core/block.py:213-219` (`Block.text`, `Wrap.NONE` — the default) | text wider than `width` | tail chars | NOTHING — only `Wrap.ELLIPSIS` marks | visual clipping | **EXEMPT** (ruled: `Wrap.NONE` default is the declared clipping contract) | `test_law6_silent_exemptions_are_real_and_shrink_only` (+ `test_block_extended.py:87-118` ELLIPSIS) |
| 10 | `views/record.py:243` (MINIMAL) | summary wider than `width` (via `Block.text` Wrap.NONE) | tail of gist | NOTHING | visual clipping | **MARKED (0.14 S5)** — `record_line` MINIMAL marks its own summary cut (the caller owns it; `Wrap.NONE`'s exemption does not transfer) | `TestLaw6EvidencePins::test_record_minimal_marks_the_cut_and_is_clean_when_it_fits` |
| 11 | `views/lens/tree.py:163-164` (`content_width <= 0: continue`) | deep nesting / narrow width exhausts indent budget | entire child rows/subtrees | NOTHING — row skipped | allocation (width) | **MARKED (0.14 S3)** — `… N nodes hidden` (exact zoom-visible count, per dropped run) | `TestLaw6EvidencePins::test_tree_subtree_drop_marks_exact_count` |
| 12 | `views/lens/tree.py:175,192,209,236` | node content wider than remaining col | node tail | ellipsis only if `content_width>1`; at width 1 bare `truncate` (no marker) | visual clipping | MARKED; **width-1 EXEMPT** (ruled: physical-space waiver — no room for content + marker) | `TestLaw6EvidencePins::test_tree_row0_tail_ellipsis_marks_and_width1_waives` (+ ratchet for the waiver) |
| 13 | `views/lens/flame.py:206-217,248-269` (`seg_w<=0: continue`; `truncate(label, seg_w)`) | segment too narrow for its proportion; label wider than segment | dropped segments; label tail | NOTHING — plain `truncate` drops chars; sub-min segments vanish | allocation (width) | **MARKED (0.14 S4)** — dropped positives fold into a muted `+N` remainder tail; labels ellipsize | `TestLaw6EvidencePins::test_flame_remainder_marks_exact_merged_count` |
| 14 | `core/compose.py:278-299` (`border` title) | `block.width < title_width + 3`, or `pos > block.width` mid-loop | the title (whole or tail) | NOTHING | allocation (width) | **MARKED (0.14 S5)** — title ellipsized into top-border capacity (content-before-chrome tiers), waived when no capacity | `TestLaw6EvidencePins::test_border_title_ellipsizes_and_waives` |
| 15 | `views/record.py:431,690-705` (`record_map`/`record_timeline` `width - indent`) | `indent ≥ width` → negative → `Block.text(width≤0)` → empty | the whole record line | NOTHING — line becomes 0-width | allocation (width) | **MARKED (0.14 S5)** — non-negative narrow-width degrade (exact-width marker row; row-drop waiver only when the marker cannot fit) | `TestLaw6EvidencePins::test_record_map_narrow_indent_degrades_honestly`, `::test_record_timeline_narrow_indent_degrades_honestly` |
| 16 | `core/compose.py:346-407` (`truncate`) | `block.width > width` | tail cells | ELLIPSIS (ambient `IconSet.ellipsis`, ASCII-degrading); at `width ≤ ellipsis_width`, marker alone or empty | visual clipping | MARKED | `test_compose_extended.py` |
| 17 | `core/compose.py:434-451` (`fit_to_width`) | wider than width | tail | ELLIPSIS (delegates to `truncate`) | visual clipping | MARKED | — |
| 18 | `core/block.py:221-244` (`Block.text` `Wrap.ELLIPSIS`); `_wrap_styled:764` (since renamed `_wrap_runs`) | text > width | tail | ELLIPSIS (ambient, width-aware) | visual clipping | MARKED | `test_block_extended.py:96-118` |
| 19 | `views/lens/shape.py:312-343,399-434` | `len > _MAX_DICT/LIST_ITEMS` (20) or `fidelity.lines` | trailing items | "... +N more" footer | *fidelity/policy* (item cap, not geometry) | MARKED (out of scope) | `test_lens.py:232-278,668-699` |
| 20 | `views/lens/shape.py:237-239` (`_render_scalar`) | `str` display > `fidelity.chars`/`_MAX_STR_DISPLAY` (200) | mid-string | `"... [N chars]"` then width-ellipsis | fidelity budget + width | MARKED | `test_lens.py` |
| 21 | `core/compose.py:468-527` (`budget_fields`) | fields exceed width | per-field truncation + whole-field drops | returns `dropped` count; caller renders `[+Nc]` badge — painted emits nothing itself | allocation (width) | MARKED (caller-owned) | `test_budget_fields.py:95`, `test_budget_fields_properties.py` |
| 22 | `views/components/_table.py:200-260,532-533` | col cell/table over budget | cell tail / trailing columns | `Overflow.FIT`+`ellipsis=True` → ellipsis; `Overflow.CLIP` → right-edge ellipsis (whole trailing cols vanish behind it); `ellipsis=False` → `Line.truncate` silent | allocation (width) | **CLIP column-drop MARKED (0.14 S2)** — `+Nc` wholly-hidden-column badge; **`Column(ellipsis=False)` per-cell clip EXEMPT** (ruled: declared contract) | `TestLaw6EvidencePins::test_table_column_badge_counts_wholly_hidden_columns` (+ ratchet for `ellipsis=False`) |
| 23 | `views/lens/chart.py:122,169,205` | label/stat/bar-row over width | tail | ellipsis (`_truncate_ellipsis`, width>1 guard) | visual clipping | MARKED | chart cases in `test_lens.py` |
| 24 | `inplace.py:90-135` | frame taller than terminal | none *dropped* — terminal scrolls; relative cursor addressing tears (documented `inplace.py:6-10`) | NOTHING (no height check) | allocation (height) | **MARKED (0.10)** — the tear was resolved to a head-clip with evidence: `_fit_viewport` emits `… +N rows` (RENDER_MODEL §7 Q2b, LIVE_DELIVERY_DESIGN §10) | `TestLaw6EvidencePins::test_inplace_oversized_frame_marks_the_cut` |
| 25 | `core/writer.py:293-330` (`write_ops`) | cell coord off-screen | writer emits `move_cursor` regardless; terminal clamps | NOTHING, but writer drops nothing itself | n/a (terminal-side) | out of scope | — |

**Silent paths ranked by likely user impact (2026-07-10 finding):** (1)
`Block.paint`/`Surface` height+width clipping (#1–3); (2) `list_view`/`table`
scroll windows with no affordance (#4–5); (3) `Block.text` default `Wrap.NONE`
(#9–10); (4) `Line.truncate`/`to_block` backing table cells and list rows
(#6–8); (5) `tree_lens` whole-subtree drops at narrow width (#11); (6)
`flame_lens` sub-minimum segment vanishing (#13); (7) `border` title drop
(#14) and `record_map`/`timeline` negative-width collapse (#15).

*Disposition (0.14 S1–S5): every allocation-driven decider in this ranking now
MARKS — #4–5 (viewport rows), #6 (list row tail), #10 (record MINIMAL), #11
(tree subtree drop), #13 (flame remainder), #14 (border title), #15
(record_map/timeline) — see the verdict column above for the per-path slice
and evidence pin. The rest are ruled non-deciders: the paint mechanisms #1–2,
the primitives #7–8, and the `Wrap.NONE` default #9 are EXEMPT under §4's
ownership rule. #3's raw `Surface` paint is not a separate ruled identity — it
is EXEMPT *by delegation* to #1/#2 (it is those mechanisms at the delivery
target), while a host *viewporting* #3 is a decider that draws the evidence row
(`ViewportAdapter`, 0.13 host rung). The eight ruled exemptions — and only those
eight — are pinned by the shrink-only ratchet; Surface is not among them.*

**Boundary-blur cases:** the item caps (#19: `_MAX_DICT/LIST_ITEMS=20`,
`_MAX_STR_DISPLAY=200`, overridable by `fidelity.lines`/`chars`) read as
geometry but are fidelity — the codebase's most visible omission evidence
is doing fidelity's job while the genuine allocation paths stay silent.
`_render_scalar` (#20) can fire the fidelity-chars marker and the width
ellipsis on the same string — two residues, no signal for which constraint
bound, and the `[N chars]` tail can itself be eaten by the width cut.
`table` (#22): under default `Overflow.CLIP` a user cannot distinguish an
interior column silently cut from whole trailing columns vanished behind
the one right-edge ellipsis; `Overflow.FIT` answers honestly but is opt-in.
*(Closed 0.14 S2: `Overflow.CLIP` now exposes a `+Nc` wholly-hidden-column
badge, so the whole-column loss is countable; the per-cell `ellipsis=False`
clip stays the ruled declared contract.)* `budget_fields` (#21) is
marked-capable but marking is caller-owned.

**Test-coverage note (2026-07-10):** the "+N more" footer is the only
geometry-adjacent evidence behavior with test coverage — and it is
fidelity-driven. No test anywhere asserts a marker on width clipping in the
primitive/Line/buffer layers; none asserts any height-overflow or scroll
behavior. *(Closed 0.14: `tests/unit/test_render_model_laws.py::TestLaw6EvidencePins`
now asserts the marker on every remediated allocation path — viewport rows,
row/column tails, tree/flame drops, record/border cuts — in both Unicode and
ASCII, with exact-fit byte comparisons; the ruled silent set is pinned by
`test_law6_silent_exemptions_are_real_and_shrink_only`.)*

## Law 7 — host-independence baseline

Taught signature: `README.md:59-61` and `src/painted/CLAUDE.md:74-77` both
teach `def render(ctx: CliContext, data) -> Block`, though the examples'
bodies read only `ctx.zoom`/`ctx.width`. `CliContext`
(`cli/types.py:151-190`) carries `fidelity, mode, use_ansi, is_tty, width,
height, args, stdin_is_tty, stderr_is_tty, _session`.

Inventory (25 = files declaring `def _render(ctx: CliContext, …)` under
`demos/` + `src/painted/_demo_cli.py`):

- **23/25 read only `ctx.zoom`/`ctx.width`/`ctx.fidelity.shows(...)`** —
  mechanically migratable to `(data, fidelity, width) -> Block`.
- **2/25 additionally consume output capabilities** via the `use_ansi`
  proxy, by design:
  - `demos/showcase/raymarch.py:470+` — "Capability picks the carrier:
    color terminals get the lit portrait … pipes get the luminance ramp."
    `use_ansi` selects different Block *content*.
  - `demos/showcase/starmap.py:421-424` — `_links_live = ctx.use_ansi and
    resolve_ref("star:Sirius") is not None` — a render-time link-capability
    probe.
- **0/25 dispatch on host lifecycle inside a semantic renderer.**
  *Corrected in cross-review*: the original trace classified
  `responsive.py:576` and `table.py:399` as in-render violations; both
  `is_tty` reads actually sit in `_handle_interactive` (host territory) —
  the `_render` functions (`responsive.py` delegating to
  `render_dashboard`; `table.py:272`) are clean.

Operational friction evidence: `ResponsiveSurface.render`
(`demos/patterns/responsive.py:534-548`) fabricates a fake `CliContext`
(`mode=INTERACTIVE, use_ansi=True, is_tty=True`) solely to reuse
`render_dashboard(ctx, data)` from a Surface — host facts synthesized to
satisfy a signature that only needs fidelity + allocation. Contrast the
healthy pattern in `table.py:363-383`: `TableSurface.render` calls
`render_adaptive(data, width)`, a plain function, with the CLI `_render`
as a thin adapter.

`views/` imports no `painted.cli` and references no `CliContext` —
enforced by `tests/unit/test_architecture_invariants.py:382-398`
(`_CLI_SEAMS`, frozen at two seams, neither touching `views/`).
`Surface.render(self) -> None` paints into `self._buf`
(`tui/surface.py:171-172`); `Layer` follows the same shape.

## Law 1 — ambient-input inventory

| Ambient input | file:line | Affects |
|---|---|---|
| Palette (`_palette` ContextVar) | `palette.py:192` | **Content** — bakes `Style` into cells (compose, flame, shape, traceback, record, callout, meter, sparkline, list, progress, table) |
| IconSet (`_icons` ContextVar) | `icon_set.py:121` | **Content** — selects glyph chars written into cells (compose ellipsis, chart, tree, traceback, table, spinner, sparkline, list, progress, callout) |
| Border chars (`_borders` ContextVar) | `core/borders.py:44` | **Content** — box-drawing character choice |
| Vocabulary registry (`_vocabularies` ContextVar) | `vocabulary.py:350` | **Content** — value→`Style` resolution, overflow/series behavior |
| Role overrides (`_role_overrides` ContextVar) | `vocabulary.py:434` | **Content** — consulted by `mark_style` before declared roles |
| Theme | `theme.py` (no own ContextVar) | Atomic setter of **palette + icons + borders + role overrides** — four of the five channels; NOT the vocabulary registry |
| Ref schemes (`_ref_schemes` ContextVar) | `refs.py:85` | **Serialization only** in the core path — `resolve_ref` fires once, in `core/writer.py:209` (OSC 8 emission). (`starmap`'s render-time probe is a capability read, not a core-path content dependency.) |
| `NO_COLOR`/`COLORTERM`/`TERM` | `core/writer.py:74,90,95` | Serialization only — color-depth downsampling |
| `PAINTED_SCROLL_OPTIM` | `tui/surface.py:67` | Neither — diff-strategy performance knob |
| `COLUMNS`/`LINES`, `shutil.get_terminal_size()` | `cli/types.py:236-237,308` | Orthogonal — resolves the *default* of the explicit `width` input before render is called |

Conclusion: **five** content-affecting ambient channels (palette, icons,
borders, vocabulary registry, role overrides). `refs` does not belong on
the content list; `theme` is a setter, not a channel.

## Law 4 — destination-independence verification

All `Fidelity(...)` construction sites in `src/` verified argv/declaration-
pure: `cli/types.py:833` (`parse_fidelity` — reads only `getattr(args, …)`),
`cli/runner.py:157` (declared default zoom), `cli/runner.py:287` +
`app_runner.py:49` (help path, argv-derived zoom), `core/doc.py:232`
(plain default value). `with_density` (`core/fidelity.py:56`) is a pure
`replace`. `detect_context` (`cli/types.py:258-336`) computes
`is_tty`/geometry (env `COLUMNS`/`LINES`, `shutil.get_terminal_size`,
`isatty`) into separate `CliContext` fields; the `fidelity=` field is the
untouched object passed in. The mode-collapse check (`runner.py:197`)
reads fidelity, never writes.

Gaps: (a) **ungated** — every existing `isatty` monkeypatch in the fidelity
tests exercises mode/format resolution, never asserts fidelity invariance
under TTY/geometry variation; a regression reading terminal size inside
`parse_fidelity` would pass today's suite. (b) `FIDELITY_DESIGN.md`
documents `build_fidelity`'s *position* (the last-run escape hatch) but not
the keep-geometry-out obligation on its *content*.

Specified gate: call `parse_fidelity` twice with identical Namespaces under
different `isatty`/`COLUMNS`/`LINES`, assert equal `Fidelity`; optionally a
static check that `core/fidelity.py` + `parse_fidelity` never reference
`os.environ`/`isatty`/`get_terminal_size`.

## Law 8 — no-downstream-policy verification

`core/{block,compose,cell,span,writer,buffer}.py`, `inplace.py`, and
`tui/` are fidelity-free by direct import inspection (the "depth" hits in
`writer.py` are `ColorDepth` — terminal color capability, an unrelated
concept sharing the word). `core/fidelity.py` imports only stdlib
dataclasses — a pure leaf spec. There is no separate TUI buffer:
`tui/surface.py:11` reuses `core.buffer.Buffer`.

The one exception: `core/doc.py:56` imports `Fidelity` and implements the
shared disclosure walk (`_eff` at 187-197, `visible_body` at 200-211,
`capped` at 214-221, `doc_lens` at 229+). Deliberate: its docstring
(doc.py:1-42) explains the core placement (a *document* compositor over a
fixed vocabulary, peer of `compose.py`, letting `cli/help.py` and the docs
front door share it without a cli↔views crossing); its names are kept out
of `core.__all__`.

Gap: **held by discipline, not construction** — the architecture tests
check only cross-layer direction; `compose.py` adding
`from .fidelity import Fidelity` would pass every existing test.

Specified gate: `_assert_no_imports` (existing helper,
`test_architecture_invariants.py:62`) over
`{block,compose,cell,span,writer,buffer}.py` + `inplace.py` +
`tui/{surface,layer}.py`, forbidding `painted.core.fidelity` and
`painted.cli.types`, with `core/doc.py` explicitly allowlisted and
commented as the named exception, `_CLI_SEAMS`-style.
