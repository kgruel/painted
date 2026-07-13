# Refs — the denotation channel reaches every delivery

**Status: IMPLEMENTED 2026-07-05, ships in 0.7.0** (branch
`ref-deliveries`). The per-cell
denotation channel has existed since v0.1.2 — `Block.text(id=)`, per-cell
grids threaded through every compose op, `Buffer.put_id`, `Surface.hit` —
but only one delivery reads it: TUI hit-testing. This document names the
channel (`ref`), declares its resolver seam (`RefScheme`/`use_refs`, spec'd
in VOCABULARIES_DESIGN §6), and wires the two missing readers: OSC 8
hyperlinks in ANSI deliveries and anchors in HTML. Companion decision,
ratified for this release: the *design* covers the general per-cell
annotation channel so mark persistence (`roadmap/mark-persistence`) slots
in later without reshaping these seams — but only the ref reader ships.

## 1. The evidence — what exists, what's missing

The research pass (2026-07-05, seven tracers) corrected the roadmap's
assumptions:

1. **The channel is built, not half-built.** `Block` carries a two-tier
   annotation: `id: str | None` (uniform whole-block, zero-allocation) and
   `_ids` (per-cell override grid, exact `_rows` mirror, validated at
   construction — `block.py:116-125`). Every compose op threads it:
   `join_horizontal`/`join_vertical`/`pad`/`border`/`truncate`/`vslice`,
   each with an id-free fast path and a grid-building path. `Block.paint`
   moves it into `Buffer._ids` (flat, lazily allocated); `Buffer.hit` /
   `Surface.hit` read it. Test coverage is real
   (`test_hit_testing.py`, `test_compose_extended.py` exercise per-cell
   grids through every op).
2. **Only one of five deliveries reads it.** TUI hit-testing consumes the
   channel; ANSI, HTML, PLAIN, JSON ignore it. PLAIN and JSON are correct
   to ignore it (a plain pipe can't express a link; JSON is the data, not
   a picture of it — see MODE_RESOLUTION / the four-channel model). ANSI
   and HTML are gaps: both terminals (OSC 8) and the docs site (`<a>`) can
   express denotation, and don't.
3. **Zero consumers use the channel today.** loops, siftd, and
   loops/apps/hlab were grepped: no `id=`, no `put_id`, no `Surface.hit`,
   no `render_html`. loops pins `<0.5`, siftd locks `0.4.0`. The naming
   pass costs painted-internal churn only (src 17 sites, tests ~58,
   demos ~9 — counts include the unrelated `Focus(id=)` sites that stay).
4. **The word is already ratified.** The four meaning channels on the 1.0
   `paint()` contract are disclosure / arrangement / **denotation** /
   mark, and denotation's parameter is `ref` (keystone arc, 2026-07-04).
   VOCABULARIES_DESIGN §6 spec'd `RefScheme` under that name. The code
   says `id`. One channel, one word: the code moves.

## 2. The channel contract

A **ref** is an opaque per-cell string annotation — denotation, never
behavior. It answers "what does this cell *refer to*?" and nothing else:
no styling (that is mark's job), no layout (arrangement's), no visibility
(disclosure's). painted moves refs and hands them to deliveries; it never
interprets them beyond the resolver seam below.

Per delivery:

| Delivery | Reads ref as | Status |
|---|---|---|
| TUI | hit target — `Surface.hit(x, y) → str \| None` | shipped (v0.1.2, mouse work) |
| ANSI | OSC 8 hyperlink, only when a declared scheme resolves it | **this release** |
| HTML | `<a href>`, only when a declared scheme resolves it | **this release** |
| PLAIN | nothing — dropped | permanent |
| JSON | nothing — JSON is the data, refs annotate the picture | permanent |

**Survival rule** (already true, now stated as contract): refs survive
every Block operation that moves cells — construction, join, pad, border,
truncate, vslice, paint. Overwriting a cell without a ref clears the ref
(`Buffer.put`/`put_text` null the slot): an annotation is only as fresh as
the last paint.

## 3. The naming pass — `id` becomes `ref`

**D1 — every channel spelling renames; old spellings become deprecated
aliases, removed at 1.0.** The rename rides the same law as
`show()`→`paint()` (0.8): land the new word in a minor, keep the old as a
`DeprecationWarning` alias, flip all internal docs/demos/tests in the same
change, remove at the major. Zero external consumers means the alias costs
almost nothing, but the ceremony is kept because the law is the point —
consumers who adopt 0.7 get the same migration contract everywhere.

| Old | New | Alias mechanics |
|---|---|---|
| `Block.text/column/empty(…, id=)` | `ref=` | `id=` kwarg accepted, warns, forwards |
| `Block(…, id=, ids=)` | `ref=`, `refs=` | same |
| `Block.id` attribute | `Block.ref` | `id` property alias, warns |
| `Block.cell_id(x, y)` | `Block.cell_ref(x, y)` | method alias, warns |
| `border(…, id=)` | `ref=` | kwarg alias, warns |
| `Buffer.put_id(…, id)` | `Buffer.put_ref(…, ref)` | method alias, warns |
| `BufferView.put_id` | `BufferView.put_ref` | same |
| `Buffer._ids` / `Block._ids` | `_refs` | private — renamed outright, no alias |
| `Surface.hit` | unchanged | already the right name; returns the ref |

Aliases warn with `DeprecationWarning`, `stacklevel` aimed at the caller,
and are pinned by tests (both the forwarding and the warning). The
public-api guard keeps `Block`/`Buffer`/`border` names; kwarg renames
don't trip it, which is exactly why the alias-plus-warning discipline is
enforced by test instead.

**Non-renames, stated so nobody over-rotates:**

- **`Focus.id` stays.** It names a focus-ring target, a different concept
  in a different subsystem. The law is "one word for the per-cell
  channel," not "no `id` anywhere."
- **`Surface.hit` stays** — and `docs/MOUSE.md`'s phantom `hit_test`
  spelling is corrected to match the code in this pass.

**D2 — `Code.ref` renames to `Code.src` in the same change.** The doc-IR
`Code(ref="py:painted.cell:Style#definition")` field is an authoring-time
content *locator*, not a render-time denotation (`code-ref-reconcile`,
resolved 2026-07-05). If the channel takes the word `ref`, leaving
`Code.ref` in place would recreate the exact two-concepts-one-word
collision this pass exists to clear — dissolution isn't done until the
residue is swept, in the same change. Usage is four sites (field, the
publisher reader — now `painted/publish.py` — and two tests), zero
consumers. Same alias law:
`ref=` kwarg accepted with a warning through 0.x, removed at 1.0.

## 4. Ref syntax and the resolver seam

**D3 — a ref optionally carries a scheme: `"scheme:value"`, split on the
first colon.** `"fact:01JQ8F…"` has scheme `fact`; `"sidebar"` has no
scheme. Scheme-less refs are the hit-testing idiom and stay fully
supported — they are simply inert in link deliveries, which is the correct
degradation: a button target is not a URL.

**`RefScheme` — the declaration** (verbatim target shape from
VOCABULARIES_DESIGN §6):

```python
from painted import RefScheme, use_refs

use_refs(RefScheme("fact", lambda value: f"https://loops.dev/f/{value}"))
```

- Frozen dataclass: `name: str` (kebab-case, same `_NAME_RE` discipline as
  `Role`), `resolve: Callable[[str], str | None]`. The resolver receives
  the ref's value part (after the colon) and returns a URI or `None` —
  `None` is a legal "no URI for this one," which a bare template string
  cannot express. No styling field, ever: link color is the delivery's
  concern; a ref that wants categorical color is carrying a vocabulary
  mark alongside its ref (§6 of the vocabularies doc).
- **Validation at construction** (`DeclarationError`): bad name shape,
  non-callable resolver. The 0.6 external-review mandate — *validate every
  declaration, tolerate all data* — applies from day one.
- **Registration**: `use_refs(*schemes)` — same dual setter/context-manager
  shape as `use_vocabularies`, REPLACE semantics, duplicate-name collision
  raises `DeclarationError` at the call. Single-layer ContextVar (like
  `_palette`, unlike `_vocabularies`): there is no built-in ref scheme the
  way `severity` is a built-in vocabulary, so no two-layer merge.
  `current_ref_schemes()` / `reset_refs()` complete the set.
- **Resolution choke point**: one function, used by every link delivery:

  ```python
  def resolve_ref(ref: str) -> str | None:
      scheme, sep, value = ref.partition(":")
      if not sep:
          return None                    # scheme-less → inert
      declared = current_ref_schemes().get(scheme)
      if declared is None:
          return None                    # undeclared scheme → inert
      return declared.resolve(value)     # may itself decline with None
  ```

  **Inert, not raise, on undeclared schemes** — the one deliberate
  asymmetry with `mark_style` (which raises `ContractError` on an
  undeclared vocabulary). A mark without its Style is a rendering gap; a
  ref without a URI still renders its content perfectly — the honesty rule
  is *"no declared scheme → refs stay inert in every delivery; painted
  never invents URIs"*, and inertness is the rule's own word.
- **A resolver that raises propagates unwrapped.** The resolver is app
  code; a fault inside it is the app's, and `PaintedError` means "painted
  itself detected this." Wrapping would misattribute. (Contrast: painted's
  own declaration checks raise `DeclarationError`; that boundary is
  painted's.)
- **Module home: `src/painted/refs.py`**, sibling to `vocabulary.py`.
  `core/writer.py` and `core/html.py` import it the same way writer
  already imports `..palette` — the established core→renderer-ambient
  seam. Exported from `painted.__all__` (`RefScheme`, `use_refs`,
  `current_ref_schemes`, `reset_refs`, `resolve_ref`), same tier as the
  vocabulary exports. Zero CLI imports, structurally — ref schemes
  generate no flags (vocabularies rule 4 applies identically).
- **The framework-tier declaration**: `use_refs`/`current_ref_schemes` above
  is the renderer-ambient seam a lens reads. `run_cli`'s `ref_schemes=`
  (docs/RENDERER_CONTRACT_DESIGN.md §7) is the CLI framework's own
  declaration of the same channel — static or callable, installed as a
  per-cycle bracket around fetch/render/flush so a run's ambient state can
  never leak into the next. The two are the same resolver seam at two
  altitudes: `use_refs` for a renderer authored directly against the
  library, `ref_schemes=` for one authored against `run_cli`.

## 5. ANSI delivery — OSC 8

Emission form: open `\x1b]8;;{uri}\x1b\\`, close `\x1b]8;;\x1b\\` (ST
terminator, not BEL). Three gates, all must pass:

1. **Honesty**: `resolve_ref(ref)` returned a URI. No scheme, undeclared
   scheme, resolver-declined → zero bytes emitted; the ref stays inert.
2. **Format**: ANSI path only. `print_block`'s plain branch and
   `use_ansi=False` never see the writer.
3. **Opt-out**: `Writer(…, hyperlinks: bool = True)`. OSC 8 is
   progressive enhancement per the capability-council doc — unsupporting
   terminals ignore the wrapper and render the text, the same posture as
   the mode-2026 sync markers `write_ops` already emits unconditionally —
   so there is no detection, only an explicit off switch, mirroring the
   `color_depth=` constructor override rather than `detect_color_depth`.

**Resolver output is data, and the writer tolerates all data**: the URI is
percent-encoded before splicing (bytes outside printable ASCII; RFC 3986
reserved/unreserved characters and `%` pass through), so a resolver cannot
inject control bytes — a stray ESC or BEL would otherwise terminate the
OSC 8 early and hand the terminal an attacker-shaped second sequence. An
empty-string URI is treated as no URI (inert): OSC 8 with an empty target
*is* the close sequence, and letting it through would desync the
open/close state machine.

**Both emission loops gain a `last_ref` tracker parallel to `last_style`**
— they are independent state machines; a ref-only transition must emit
even when style is unchanged (the `writer.py:219` gotcha):

- `Writer.write_ops` (Surface/StreamSurface/TUI path): tracker resets on
  `ScrollOp` alongside `last_style`; any still-open link closes before the
  final reset. Non-adjacent cell writes (cursor jumps) close the link —
  a hyperlink region must not bleed across cells the frame didn't write.
- `render_row_ansi` (print_block/InPlaceRenderer path): the row-span walk
  passes the ref row into `iter_trimmed_row_spans(row, refs)` — the
  iterator has taken an ids argument since the mouse work; the ANSI reader
  simply starts supplying it. Any open link closes at row end, before
  `reset_style` — an OSC 8 must never leak across a newline.

**The change stream becomes ref-aware.** `CellWrite` gains
`ref: str | None = None` (additive, frozen dataclass default), and
`Buffer.diff` compares ref slots whenever either buffer has a ref grid
allocated. This closes the documented blind spot — same char, same style,
different ref produced no `CellWrite`, so a TUI frame could leave a stale
link on screen. Cost: one extra comparison per differing cell, and
ref-only changes now redraw a cell that draws identical bytes when no
resolver is declared — a correctness-over-convenience trade taken
knowingly (the alternative, diffing conditionally on resolver presence,
couples the buffer layer to ambient state; refused).
`InPlaceRenderer`'s same-height row-equality check gets the same
treatment: row comparison includes the ref row, so an in-place rewrite
can't skip a row whose only change is denotation.

## 6. HTML delivery — anchors

`render_html` starts passing the ref grid into `iter_row_spans` and gains
an anchor state machine alongside the existing `last_css`/`span_open`
one. Rules:

- Resolution through the same `resolve_ref` choke point, read ambiently —
  **no signature change** to `render_html(block)`; the resolver seam is
  ambient state exactly like the palette, so the docs-site pipeline
  (`./dev panels` → outputgen) picks refs up without threading a
  parameter through `tools/`.
- Nesting discipline: `<a>` wraps `<span>` — on a ref transition, close
  the open style span, close the anchor, open the new anchor, reopen the
  span. Never interleave.
- `href` escaped with `quote=True`, same as the style attribute; anchor
  text content stays on the existing `_html.escape` path.
- Unresolved refs emit nothing — no `<a>`, no data-attribute. (A
  `data-ref` attribute for unresolved refs is mark-persistence-shaped
  territory — annotation persisting into the artifact — and is explicitly
  deferred to that design rather than half-shipped here.)
- Anchor transitions key on the *ref*, not the resolved href — mirroring
  the ANSI writer's `last_ref` — so a ref change re-anchors even when two
  refs resolve to the same URI.
- The anchor balance and href-escaping property laws live in
  `tests/property/test_html_refs.py` (their own file, so the ANSI writer
  laws and the HTML anchor laws evolve without collision); the
  appearance-tier serializer gains the ref dimension (see §8).

## 7. Design general, ship refs — the general annotation channel

Ratified scope for 0.7 (Kyle, 2026-07-05): the design covers the general
per-cell annotation channel; only the ref reader ships. What that means
concretely — three seams are shaped now so the mark channel
(`roadmap/mark-persistence`) is a second tenant, not a second system:

1. **The movement contract is annotation-generic.** The complete set of
   sites that co-move "a row of cells" and "a row of annotations" is
   enumerated (construction/freeze, the six compose ops, `Block.paint`
   fast + span paths, `Buffer.put*`/`scroll_region_in_place`/`clone`, the
   three `_row_ops` iterators). These helpers are already parameterized
   over an annotation row (`iter_row_spans(row, ids)`) rather than
   hardcoded to refs — that parameterization *is* the general channel's
   mechanics, and this release keeps it that way. A future channel reuses
   the same helpers; it does not add parallel branch logic per op.
2. **Emission loops follow a tracker-per-channel discipline.** Each
   run-coalescing loop (`write_ops`, `render_row_ansi`, `render_html`)
   holds one `last_<channel>` tracker per channel it reads, transitions
   independent, closes in reverse-open order. `last_style` + `last_ref`
   are the first two; `last_mark` (HTML classes / CSS custom properties)
   is specified to join the same way.
3. **Storage stays bespoke for ref; channel #2 triggers the
   generalization decision.** The ref grids keep their hot paths (the
   uniform-default promotion, slice-assignment paint, lazy buffer
   allocation) — hit-testing runs per-frame and earned them. When the
   mark channel lands, the choice is: a generic named-channel store
   (`Mapping[str, grid]`) beside the ref arrays, or ref migrating into
   it — decided *then*, with profiling, against a movement contract that
   is already pinned and identical either way. Deciding storage now,
   without the second tenant's real shape, would be speculation; the
   dissolution pressure (two annotations → one mechanism) is honored at
   the contract level, where it's load-bearing, not the slot level, where
   it isn't yet.

What is *refused* now: building any mark persistence (role-carrying
cells, CSS class emission, re-theming artifacts) in this release. The
direction-p0s-audit warning applies — this is annotation delivery, not an
output envelope, and marks aren't annotations yet.

## 8. Tests and gates

- **Unit**: alias forwarding + `DeprecationWarning` for every renamed
  spelling; `RefScheme`/`use_refs` declaration validation
  (`DeclarationError` cases); `resolve_ref` inertness table (no colon /
  undeclared / resolver-declines / resolves); OSC 8 open/close placement
  in both loops (row end, scroll reset, cursor jump, stream end); diff
  ref-awareness (the same-glyph-different-ref scenario emits a write).
- **Property**: extend the writer laws — no unterminated OSC 8 in any
  `render_block_ansi` output; plain mode still emits zero escapes;
  HTML anchor balance + href escaping under adversarial ref strings.
- **Appearance**: the snapshot serializer (`tests/appearance/conftest`)
  gains the ref dimension — without it the tier is blind to refs exactly
  as the legacy goldens were blind to Style. Snapshot files regenerate.
- **Outputgen**: `render_html` output changes only for blocks that carry
  resolvable refs; a refs specimen panel is added so the docs site
  demonstrates the feature and the gate pins it. `./dev panels` + commit.
- **Cohesion/arch**: `refs.py` imports nothing from `painted.cli`
  (structural pin, same as vocabulary's); raise sites classified
  (`test_raise_sites_use_painted_exception_classes` already gates this).

## 9. Compatibility and version

0.7.0, semver-MINOR: every rename ships behind a warning alias (the old
spelling keeps working through 0.x), new API is additive (`RefScheme`,
`use_refs`, `current_ref_schemes`, `reset_refs`, `resolve_ref`,
`Writer(hyperlinks=)`, `CellWrite.ref`), and no delivery emits new bytes
unless an app declares a scheme — an app that upgrades and declares
nothing sees byte-identical output everywhere except the new
`DeprecationWarning`s on old spellings. Consumers (loops `<0.5`, siftd
`0.4.0`) are behind the current floor regardless and migrate on their own
floor-bump schedule. Alias removal lands at 1.0 with the `show()` alias
removal — one deprecation horizon, stated in the changelog.

## 10. Deferrals — named, with triggers

- **`Line`/`Span` refs**: the styled-span composition path (`Line.wrap`,
  `_wrap_styled`) has no ref concept and produces ref-less Blocks.
  Trigger: the first consumer composing ref-carrying text through spans.
  (`Line.paint` clearing refs on overwrite is correct behavior, not part
  of this gap.)
- **Mark persistence**: own design, riding the seams shaped in §7.
  Trigger: already ratified as a want (`roadmap/mark-persistence`);
  sequencing after 0.7 was Kyle's scope call for this release.
- **`Code.src` resolver** (docgen resolution of the renamed locator):
  unchanged deferral from `code-ref-reconcile`; when built, it should
  stamp resolved code Blocks' cells with source *refs* — the composition
  bonus falls out of this release's machinery for free.
- **Per-ref styling, link decoration, `data-ref` attributes**: refused —
  denotation never carries appearance; see §4 and §6.
