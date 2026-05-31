# painted — the width contract (what "width" actually means)

> **DECISION (ratified 2026-05-30): a passed `width` is EXACT — pad up / wrap-then-pad,
> never overflow horizontally; an absent `width` is natural. F1, F2, and FULL are FIXES,
> not blesses. This settles the contract-review's R7.**
>
> **IMPLEMENTED 2026-05-30 (branch `fix/width-contract`).** Contract stated in
> CLAUDE.md ×2 + PRIMITIVES; `fit_to_width(block, w)` added to `compose` (= truncate-if-wide
> / pad-if-narrow) and applied at the drifting return sites of `record_line` (SUMMARY/DETAILED
> fit; FULL header fits, fields wrap-then-pad via `Wrap.WORD`) and `shape_lens._render_list`.
> Law flipped to assert exact (`w≥1`); floor guards deleted and replaced with `@example` pins
> (derandomize won't re-sample the corner — see [[test-suite-arc]]); added a FULL wrap-vs-
> truncate test AND a composition-level width law. THREE findings fell out, all fixed on the
> branch: (1) **the composers** (`record_line_composed`/`record_map`) overflowed by +2 — an
> unbudgeted attention marker — which is the level the real annoyances actually live at; leaf
> exactness does NOT propagate through untested composition, so each composer now `fit_to_width`s
> its own return (the composition law locks it); (2) `flame_lens` had the same underfill bug
> (off-by-one, val≤0 last segment loses the floored remainder) — same `fit_to_width` remedy;
> (3) `tests/property/conftest.py` never read `HYPOTHESIS_PROFILE`, so the documented `thorough`
> sweep was unreachable — wired it, and the now-real 1000-example exploration is what surfaced
> the flame bug. Full gate + 39-law thorough sweep green.

*Working note, 2026-05-30. Untracked. Grew out of the contract-and-architecture
review's F1/F2/R7 — the question "what is the width law?" turned out to have no single
answer. This maps every width-bearing surface, names the conflation, shows the mechanism
that turns it into visible misalignment, and proposes the one rule that dissolves it.*

---

## TL;DR

There is **no single width contract.** The word `width` carries **four incompatible
meanings** across the renderer, layered on top of **two conflated axes**:

- **Axis 1 — measurement vs dimension.** "Width-aware everywhere" (the documented
  invariant) is *only* a measurement claim: count display columns correctly via wcwidth,
  `display_width != len()`. It says **nothing** about whether a produced block's width
  relates to a *requested* width. The codebase treats "width-aware" and "honors width" as
  the same property. They are different claims, and only the first is ever documented.
- **Axis 2 — once dimension matters, which relation?** `block.width == width` (exact),
  `<= width` (cap), `>= width` / unbounded (floor/grow), or "ignore the arg, size to
  content" (natural). All four are live, in different surfaces, under one parameter name.

The fix is not "bless or fix F1/F2" finding-by-finding. It's: **pick one contract, make
every surface obey it, and rename the genuinely-different request.** F1/F2 then fall out as
*fixes*, because they already violate the contract the rest of the system keeps.

---

## The four meanings, by surface

| Meaning | `block.width` vs requested | Surfaces | Evidence |
|---|---|---|---|
| **exact** | `== width` | Block core (construction), `chart`/`tree`/`flame` lenses, `shape_lens` (w≥8), `progress`, `sparkline`, `record_line` MINIMAL | `block.py:127-129` (constructor rejects any row != width); lens rows via `Block.text(..., width=w)` + `join_vertical`; `progress.py:64-70`; `sparkline.py:74`; `record.py:228` |
| **cap** | `<= width` (may underfill) | `compose.truncate`, `list_view`, `table`, `Wrap.WORD`, **and the docs** | `compose.py:342-344` (returns unchanged if already narrower); `list_view.py:115-117` (`min(max_width, width)`); `table.py:207-210` (truncate only when `result.width > width`); `ZOOM_PATTERNS.md:15` ("available horizontal space") |
| **floor / grow** | `> width` | `record_line` FULL (never truncates), `record` `meta_width+10` floor, `shape_lens` list prefix at narrow w | `record.py:338` (FULL, no width arg, no truncate); `record.py:248` (`max(width-meta_width, 10)`); `shape.py:282,286` (natural-width `- ` prefix summed onto floored content) |
| **natural** | ignores arg, sizes to content | `Block.text(width=None)`, `Block.column`, `record` SUMMARY/DETAILED content segment, `shape_lens` list item | `block.py:170-184`; `block.py:250-259`; `record.py:276,298` |

**The signature is the secret contract.** Components encode intent in the *arg shape*:
required positional `width` ⇒ "I fill exactly this" (progress, sparkline); optional
`width=None` keyword ⇒ "content-sized unless you cap me" (list_view, table). The convention
exists — it's just implicit, unstated, and not followed by `record_line`.

---

## Why it bites: compose is *correct*, so it amplifies the drift

The composition layer does exactly the right thing — and that is precisely what turns a
wrong-width block into a visible defect:

- `join_horizontal` width = **sum** of child widths (`compose.py:43`) — concatenates at
  natural width, never re-clips to a target.
- `join_vertical` width = **max** of child widths (`compose.py:124`) — pads narrower
  children up to the widest, never to *your* target.
- `border` width = `block.width + 2` (`compose.py:246`) — wraps the actual width.
- `truncate` only shrinks, **never pads up** (`compose.py:344`).

None of them re-impose the caller's requested width. So a block that came back the "wrong"
size has its error **faithfully propagated** into every column seam, border box, and pane
edge downstream. The compose layer **and every lens** assume each child is exactly the width
you asked for — true for Block core, `chart`/`tree`/`flame`/`shape`(w≥8), `progress`,
`sparkline`; false for `record_line` and narrow `shape_lens`. The surfaces that break the
assumption are exactly the ones that look broken.

---

## The annoyances (empirically reproduced)

1. **Border too narrow.** `border(record_timeline(short_recs, w=60))` → a **25-wide** box,
   37 columns narrower than the rest of a UI drawn at 60. (record underfills → border wraps
   the underfill.)
2. **Shifted column / ragged seam.** `join_horizontal(record_line(w=25), chart(w=25))`:
   record underfills to 17, so the chart column starts at x=17 not x=25; the row is 42 not
   50 — jagged seam, dead space on the right.
3. **Overflow past the pane/terminal.** `record_line` FULL at `width=8` returns width
   **97** — blows past any boundary, by design ("data completeness wins").
4. **Underfilled narrow column.** `shape_lens` on a string/nested list in a thin pane
   (w≤2, or a nested value column where `width//2` drives the value col to 1–2) returns
   *wider* than asked.

**Common thread:** you build a layout trusting `block.width == width` (most renderers
honor it), and the one that doesn't — `record_line`, occasionally narrow `shape_lens` —
gets its error amplified by the correct compose ops into a visible misalignment.

## Blast radius (which one is actually hurting you)

- **F2 (`record_line`) is the villain.** It bites at *normal* widths: underfill at w=60,
  overflow whenever `width < meta_width+10` (≈25), unbounded growth at FULL.
- **F1 (`shape_lens`) is marginal.** The floor only bites at w∈{1,2} (string / single-nested)
  and w∈{1..4} (multi-row nested at z3) — widths nobody renders a real pane into. It is a
  genuine contract violation, but a degenerate-input one.

---

## Resolution — two contracts, not four

There are only **two** contracts once you apply the dissolution test. "cap" and "floor" are
not primitive meanings — they're derived or broken:

> **A passed `width` is exact: pad short rows up to it, and wrap-*then-pad* (grow height,
> every wrapped row padded to width) rather than overflow down. An absent `width` (`None`)
> means natural — size to content. That's the whole contract.**

- **exact** = the meaning of a passed `width` — already what Block core + every lens +
  progress + sparkline + record MINIMAL do. Composition's assumption becomes a guarantee.
- **natural** = the *explicit absence* of a width request (`width=None`). Not a third
  contract — "I didn't ask for a width." Clean line: pass width → exactly that width; omit →
  content size.
- **cap dissolves.** "fit, but don't exceed" is not a new contract — it's
  `truncate(render(width=None), n)`: render natural, then truncate, **both primitives you
  already have.** So `table`/`list_view` don't need a `width`-as-cap parameter; a `max_width`
  kwarg (if wanted at all) is sugar for that composition, not a fourth meaning. Per the
  dissolution test, the contract space is two, and the cap is a one-liner on top.
- **floor/overflow is the one thing that's just broken** — and the fix is wrap-*then-pad*,
  not wrap alone. (Plain WORD-wrap is itself a cap: it underfills short rows. If FULL just
  wrapped, F2's underfill reappears one row down. Wrapped rows must be padded to width.)

### F1 / F2 reframed

R7 asked "fix vs bless F1/F2" as two independent policy calls. For F1/F2-SUMMARY/DETAILED
that's the wrong altitude — pick the contract once and they stop being policy:

- **F2 SUMMARY/DETAILED → fix.** Pad the content segment to width; drop the `meta_width+10`
  floor (or wrap-then-pad instead of overflow). Width becomes exact, restoring the
  zoom-invariance F2 found missing.
- **F1 → fix (cheaply).** Clamp the `- ` prefix into the width budget instead of summing it
  on top. Trivial under the rule. Only bites at w≤4, so "bless + document" is defensible —
  but the fix is small enough that blessing buys nothing.

### FULL — the code answers the one open question

`record_line` FULL's overflow *looks* like a deliberate choice — the comment at
`record.py:343-345` accepts terminal wrapping so FULL shows complete values. The question was
whether FULL is ever composed into a fixed-width region or always a top-level dump. **The
composing primitives settle it: FULL is composed, and they assume it honors width.**

- `record_map:630` explicitly enables `Zoom.FULL`, renders it via
  `record_line_composed(..., width - indent)`, then `pad(line, left=indent)` — FULL placed in
  an indented, width-budgeted column.
- `record_timeline:402` passes `zoom` straight through at `width - 2`, then `pad(left=2)` +
  `join_vertical`.

Both reserve width and pad as if the inner block is exactly that wide. So FULL's overflow is a
**latent bug** that contradicts its own composing callers — the `343-345` comment is a stale
local assumption the surrounding API already outgrew. **FULL → fix (wrap-then-pad), same as
SUMMARY/DETAILED.**

The only surviving design fork (weak): declare FULL *top-level-only* and make
`record_map`/`record_timeline` cap at DETAILED instead. But `record_map` deliberately enables
FULL in a composed context, so "FULL is meant to compose" is the far stronger reading. Recommend
fix, not bless.

**Blessing the rest is self-defeating:** to bless F1 / F2-SUMMARY you'd declare `width` a
*cap* — and "cap" is exactly what permits the ragged-underfill misalignment. The contract
that makes composition "just work" is **exact**; the system already keeps it nearly
everywhere.

---

## Methodology / caveats

- Map produced by an 8-way parallel read of the law files, Block core, `compose`,
  `shape_lens`, `record_line`, components, the docs, and real call sites (workflow
  `width-contract-archaeology`, 2026-05-30).
- Two agents partially disagreed on `shape_lens` floors; reconciled — the "couldn't
  reproduce" agent tested w=3..60 only, and the floor lives below 3. F1's "nested→5" wording
  refined: single-level nested floors at **3**, only multi-row `list[list[str]]` at z3 → 5.
- "Empirically reproduced" annoyances are synthetic/external-caller — no in-repo demo
  composes record blocks today, only export wiring in `views/__init__.py`.
