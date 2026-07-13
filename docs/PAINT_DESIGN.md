# paint() — the single entry, the library's name as its verb

**Status: IMPLEMENTED in 0.8.0** (design-of-record).
`show()` becomes `paint()` — the single entry point, and the 1.0 keystone:
the library's name becomes the verb you call. This document fixes the
signature, the base-case boundary, the altitude stack, and the migration.
It is the `FIDELITY_DESIGN`-before-completion pattern — the design lands
before the code, so the code has a contract to meet.

The runway (`version-runway`, ratified 2026-07-05): 0.8 lands `paint()`
with `show()` as a deprecated alias and the full residue sweep; 1.0 removes
the alias and flips the docs. `paint()` shares its deprecation horizon with
the `id→ref` aliases from 0.7 — one removal, one release.

## 1. Why `paint()` is not `show()` renamed

`show()`'s defect was never only that it guessed a chart from a list shape
(the semantic-renderer positioning bug — inference at the front door). Its
deeper defect is that it is a **dead end**. The current stack tells a
consumer: start at `show(data)`, then *graduate* to `Block`/`print_block`
when you need composition, *graduate* to `run_cli` when you need flags,
*graduate* to `Surface` when you need interaction. Four front doors, and
`show()` is the one you outgrow.

A keystone entry point cannot be a rung you outgrow. If `paint()` dead-ends
the moment you compose something, "the library's name becomes its verb" is
an empty rename. So the whole design answers one question: **what survives,
unchanged, as a throwaway script grows into a tool grows into a TUI?**

The answer is not the `paint()` call. It is the lens.

## 2. The invariant is the lens, not the call

Walk one workflow from a script to a TUI and watch what ports:

```python
# script — text is the base case; this is print().
paint("Deploying api-gateway…")

# +lens — the status object, interpreted by a lens that marks the unhealthy field.
paint(status, lens=health_lens)

# +argv (a tool) — the paint() CALL is gone; the LENS is unchanged.
def render(ctx, data):
    return health_lens(data, ctx.zoom, ctx.width)
run_cli(sys.argv[1:], render=render, fetch=get_status)

# +events (interactive) — the lens ports a THIRD time.
class StatusApp(Surface):
    def render(self) -> Block:
        return health_lens(self.state, self.zoom, self.width)
```

At the `+argv` stage the literal `paint(...)` call disappears — `run_cli`
delivers internally. So the keystone slogan is **not** "you never leave
`paint()`"; a consumer who believed that hits that stage and feels lied to. What actually
survives every step is `health_lens` — the `data → Block` function. Script,
tool, and TUI run the identical lens; only the *deliverer* around it swaps.

This is the origin thesis stated as an API. The acceptance test for painted
has always been: **"does it slot into your existing render function, or
force a rewrite?"** The lens is that render function. The invariant:

> The lens (`subject → Block`) is the portable render unit. Three deliverers
> wrap it — `paint()` (direct/static), `run_cli` (argv/tool), `Surface`
> (keyboard/TUI). You swap the deliverer; you never rewrite the lens.

The store fact (`design/paint-entry`) already phrased the keystone
carefully — *"`paint(x)` is the floor and the ceiling's first rung"* — the
floor you start on and the first rung of the climb, **not** the whole
staircase. "Never leave `paint()`" was the overclaim; "never rewrite the
lens" is the contract.

### The no-lens graduate (ratified 2026-07-07, `design/no-lens-graduate`)

The walk above starts at a lens. The consumer who starts at *no* lens —
`paint(status)`, transcription exactly right — has nothing to port when they
reach `+argv`: there is no public name for what `paint()` was doing for them,
and `lens=shape_lens` is not it (that is the *inferring* renderer, a
different behavior). The gap is real, but the export is the wrong fix: the
transcription renderer stays **deliberately unexported** — naming the default
would convert the *absence* of a claim into a claimable arrangement
(`lens=transcribe`, "the interpretation that interprets as nothing") and
smear §3's line between declining interpretation and choosing one.

The resolution is §7's own discipline: drive is orthogonal to render, so a
meaning that was valid at the static drive — "no claim, transcribe the
declared shape" — must survive the move to argv, or the axes leak into each
other at the boundary this design just separated. The default recurs at the
deliverer: **`run_cli`'s `render=` becomes optional, defaulting to
transcription.** `run_cli(argv, fetch=get_status)` is then a complete, honest
tool — declared flags, zoom and fidelity threading into transcription,
`--json` re-deriving from the fetch data (the tool *is* its data) — and the
graduate ports the base case the same way they held it: by not passing a
render. You write your first lens at the moment you make your first *claim*,
and that lens is the artifact that ports onward to `Surface` (§2). It also
completes §5's wearing-a-framework table: `run_cli` wears the whole verb,
base case included, instead of only wearing it once handed a render.

Deferred — additive on the evolving `cli` surface, not part of the 0.8
`paint()` entry work. Trigger: the first real no-lens graduate (loops'
migration is the named candidate).

> **Amendment (0.11, docs/RENDERER_CONTRACT_DESIGN.md).** The no-lens graduate
> landed, but not as an *optional* `render=`. The renderer contract minted a
> new keyword-only seam, `renderer=` — `(data, fidelity, width) → Block` — and
> the transcription default installs there when neither `render=` nor
> `renderer=` is declared. `render=` itself stays exactly as required as it
> always was; it did not become optional, and it is not the seam the default
> hangs off. The prediction here (a base case reachable by omitting the
> render) is realized, but through a new named contract, not through relaxing
> the old one.

## 3. The base case is transcription, not "text only"

`show()` led with shape dispatch: `show({...})` guessed key-value,
`show([1,2,3])` guessed a chart. The chart guess is the sin — it is a claim
about what the data *means* that the caller never made. But rendering a dict
*as a dict* is not a guess; it is a transcription of what the value *is*.

So the base-case boundary is **transcription vs interpretation**, not text
vs structure:

| Subject | `paint(x)` with no lens | Why |
|---|---|---|
| `str` | the text | it is already its own rendering |
| `Exception` | the traceback as a record tree (`render_traceback`) † | structure is intrinsic |
| `Block` | the cells, delivered | it is already painted |
| `dict` | keys and values, as themselves | it declares key→value pairs |
| `list` / `tuple` | the items, as themselves | it declares order |
| `dataclass` / `NamedTuple` | its declared fields, as themselves | the type declares named fields |
| `Enum` | `Type.MEMBER` | a named member of a named type |
| `set` / `frozenset` | its members, as tags (`[a] [b] [c]`) | it declares membership, not order — `frozenset` joins `set` in this cut |

A **lens** is required only for *interpretation* — arrangement that
reinterprets the subject as something other than itself: `paint([1,2,3],
lens=chart_lens)` claims "these are a series worth plotting." `paint()`
never makes that claim on its own. Shape inference survives exactly where
the positioning work put it — as an explicitly-invoked exploration lens
(`lens=shape_lens`), never the default.

The rule, stated once: **`paint()` transcribes the shape a subject
*declares*; it refuses to invent a shape the subject does *not*.** A dict
declares pairs, a list declares order, a dataclass declares named fields —
all transcribed. A bare list does *not* declare "a series"; nested dicts do
*not* declare "a tree drawing" — those are inventions, refused here and
reachable only through an explicit lens. The declared-vs-invented line is
the same line that made `show()`'s chart-guess the sin (§1): the caller who
wrote `[1, 2, 3]` never declared it a series, but the author of a
`dataclass` *did* declare its fields.

Two consequences fix the base case. **Transcription recurses as
transcription:** a numeric list nested inside a transcribed dict stays
items, never a chart — `paint()` never infers at *any* depth. And **"declared
shape" means _stdlib_-declared** (`dataclass`, `NamedTuple`, `Enum`);
third-party schema types (pydantic, attrs) are a deferred lane (trigger: a
second consumer), not reached without a lens — so the net stays principled,
not open-ended.

**Deferred in 0.8** (both ratified 2026-07-06 after cross-family review; each
is design-intent above, not yet implemented):

- **† `Exception` → `render_traceback`.** 0.8 renders `str(exc)` (the message).
  The framework-worn path — `install()` / `PaintedHandler` (§5) — already
  renders full tracebacks, so *direct* `paint(exc)` is the rare case; it waits
  on demand rather than pulling the traceback machinery into the front door now.
- **Container dispatch keys on the _concrete_ `dict` / `list` / `tuple`**, not
  `abc.Mapping` / `abc.Sequence`. An abstract `Mapping` (e.g. `MappingProxyType`)
  or `Sequence` (e.g. `range`) renders via `str`. ABC dispatch is leaky — `str`
  and `bytes` *are* `Sequence`s, so the abstract net would have to special-case
  them back out; broadening waits on a consumer holding a genuine custom
  container.

## 4. The signature — a closed kwarg surface

The four meaning channels (`design/meaning-channels`, ratified 2026-07-04)
are the *only* semantic vocabulary `paint()` speaks: disclosure,
arrangement, denotation, mark. The signature is those channels plus the one
honest delivery param — where the paint goes:

```python
def paint(
    subject,          # what to paint (positional; the only positional)
    *,
    zoom=None,        # disclosure channel
    lens=None,        # arrangement channel
    file=None,        # delivery: where (default: stdout)
) -> None: ...
```

- **`zoom`** and **`lens`** are the two channels that are call-site
  decisions, so they are kwargs. `zoom=None` resolves to `DETAILED` — the
  base disclosure level (inherited from `show()`). A `lens` is called
  *positionally*, `lens(subject, zoom, width)`: that is the ABI every shipped
  lens satisfies (`shape_lens`, `chart_lens`, …) and the shape a custom lens
  must accept. The lens is the portable render unit (§2), so this is its
  public ABI, stated here. Precedence: a `Block` subject is already painted,
  so it is delivered as-is and an explicit `lens=` is **ignored** for it (a
  lens interprets a raw value into a Block; a Block has nothing left to
  interpret); for every non-Block subject — scalars included — the lens wins
  over the transcription default.
- **`ref`** (denotation) and **`mark`** do *not* appear as kwargs — they
  ride the *subject*. A cell already carries its ref (`Block.text(…,
  ref=…)`) and its mark; a lens stamps them on the cells it lays out. This
  is why the lens is load-bearing (§3): **mark and ref reach a non-`Block`
  subject only through a lens.** The moment you want the unhealthy field
  red (mark) or click-to-source (ref) on a raw dict, you must have a lens —
  there is nowhere on a bare Python value to hold the annotation. The lens
  is the attach-point for two of the four channels.

The **closure law** (`design/paint-entry`): the kwarg surface admits
*nothing outside the four channels plus the destination*. No `color=`, no
`title=`, no `border=`, no `width=` beyond what a lens takes internally.
Composition lives in `Block` operations; `paint()`'s kwargs are meaning or
destination, and nothing else. This is the principled form of "one
positional, no multi-arg" — `paint(a, b, c, sep=…)` is `print()` mimicry
and is refused.

Adding a fifth kwarg-channel is a **ratification event**, not an API add —
the same rule that governs the meaning channels themselves.

This closed surface is why `painted.display` (home of `paint()` and the
deprecated `show()`) joins the **semver-stable** tier alongside
`painted.core`/`painted.views`: `paint()`'s kwarg surface is a declared
public ABI, and `show()`'s removal at 1.0 is a pre-declared semver-MAJOR
event riding the deprecation horizon §9 documents — not a surprise break.

## 5. `paint()` at every altitude

The verb recurs down the stack — *paint at every altitude is meaning onto a
surface*, the surface changing with the altitude:

| Altitude | Verb | Surface |
|---|---|---|
| module | `paint(x)` | the terminal (one shot) |
| block | `block.paint(buffer)` | a `Buffer` (one frame) |
| arrangement | a lens paints | structure → a `Block` |
| atom | a `Block` paints | cells → a rectangle |

The load-bearing pair is the first two, and it resolves where "over time"
and "interactive" live **without** a `mode=` kwarg on `paint()`: the module
verb is a static one-shot; the *buffer* altitude — `block.paint(buffer)`,
run per-frame inside a `Surface` loop — is the temporal and interactive
form. The altitude stack does the work a `mode=` kwarg would have faked, and
keeps the module signature (§4) a one-shot with no lifecycle in it.

### The "wearing a framework" pattern

A deliverer is `paint()` *worn by a framework* that owns the trigger:

| Direct call | Ambient form | The framework it wears |
|---|---|---|
| `paint(block)` | `run_cli(render, fetch)` | argv + a fetch loop |
| `paint(exc)` | `install()` (excepthook) | the interpreter's exception path |
| `paint(record)` | `PaintedHandler` on a logger | the logging framework |

"Paint logs" (Kyle's base case) is almost never `paint(record)` at a call
site — you rarely hold a `LogRecord`. It is `PaintedHandler`: `paint()`
wearing `logging`, firing on every record. Same verb, one worn by a
framework. The three rows are one shape, and naming it keeps the surface
honest: each ambient form is the direct verb plus a trigger it did not have
to invent.

## 6. The single deliverer

`paint()` **subsumes** `print_block`. It accepts a `Block` and delivers it,
which makes step 0→3 of the walk one continuous verb instead of the
`show()`→`print_block` cliff. `print_block` does not vanish — it is
semver-stable — but it demotes from a *front door* to *plumbing*: the named
low-level writer that `paint()` (module altitude) and `Block.paint` (buffer
altitude) route through. A consumer reaches for it only to write bytes
without the entry-point ergonomics; the progression never sends them there.

`run_cli` is not a competing deliverer — its STATIC mode already calls
`print_block(render(ctx, data))`. It is `paint()` wearing argv. So the
library has **one** delivery path (`paint` → `print_block` at module
altitude, `block.paint` at buffer altitude); the three deliverers are three
*triggers* on that one path, not three implementations of it.

## 7. The two axes: render × drive

§5 and §6 describe delivery without naming the axis they move along. Naming
it resolves the question that keeps recurring — *is `run_cli`/`Surface` a
fifth channel?* — and that question was asked and answered in the ratifying
discussion (siftd session `01KWTRJDB3FFZ3GWCD0H07SX23`, 2026-07-04;
decisions `design/meaning-channels`, `design/paint-entry`,
`design/tui-interaction`).

painted has **two** orthogonal contracts, and the discipline is that they
are never fused:

- **Render — the four meaning channels.** `subject → Block`, parameterized
  by disclosure / arrangement / denotation / mark. This answers *what the
  subject means*, and it is invariant across every delivery: *"the same
  `render(ctx,data) → Block` serves `--static` and `-i`"*
  (`design/tui-interaction`).
- **Drive — how that render is sourced and re-sourced.** Static (channels
  bound to literals, rendered once), argv (bound to argv + TTY + a fetch
  loop, resolved once — `run_cli`), events (bound to an event stream +
  state, re-resolved every frame — `Surface`). This answers *when and from
  where the render fires*, never *what it means*.

The four channels are the render axis. `run_cli` and `Surface` are values on
the drive axis — not peers of `zoom`/`lens`/`ref`/`mark`. Folding them in
was **explicitly rejected** in the ratifying discussion:

> "`print_block` survives as writer-level plumbing (paint already delegates
> to it), and **`run_cli` explicitly does *not* fold in — it's the
> argv-driven way to arrive at the same paint pipeline, and the boundary
> between renderer and framework holds where it always has.**"
> — `design/paint-entry`, 2026-07-04

### Why a fifth channel keeps not happening

The channel set is *closed at the channel level, open at the value level*
(`design/meaning-channels`) — closing it is the `paint()` equivalent of
freezing `_CLI_SEAMS` at two. When a fifth candidate appeared in the same
session — *standing*, where a datum sits on an ordered normative scale — it
was **absorbed, not appended**: standing became *what a mark has when its
vocabulary is ordered*, and *"the channel count doesn't move."* The
precedent: a new meaning-channel candidate generalizes an existing channel;
it does not become a peer. Adding a channel remains *possible* — it is a
ratification event, not an API addition — but nothing has earned it, and a
*drive* channel specifically is a category error: it answers *how driven*,
not *what meant*.

### "Never leave `paint()`" — the two readings

The keystone slogan splits into a claim that holds and a claim that was set
aside:

| Reading | Claim | Status |
|---|---|---|
| **A — meaning unifies delivery** | interaction is a *delivery that reads the channels already in the frame*; the same `ref` is a TUI hit target, an OSC 8 link, an HTML anchor | **ratified 2026-07-04, shipped 0.7** |
| **B — one function spans all drives** | `paint(subject, …, drive=cli/events)` folds `run_cli`/`Surface` into the call | **set aside** — swallows the frameworks' declarations (honesty-rule cost), goes polymorphic in `subject`, relocates the renderer/framework boundary |

Reading A is the unification the discussion was reaching for:

> "**interactivity is not something you add — it's a delivery that reads
> meaning that was already in the frame.** The CLI→TUI progression stops
> having a seam at interaction because the interaction surface *is* the
> semantic annotation, present all along, inert where the medium can't
> express it." — siftd `01KWTRJDB3FFZ3GWCD0H07SX23`, 2026-07-04

A click resolves to a `ref` (`Click(target=ref)`, `design/tui-interaction`);
coordinates die at resolution; the *same* `ref` the TUI hit-tests is the one
ANSI emits as OSC 8 and HTML emits as `<a href>`. That is "never leave
paint" in the sense that holds: **the meaning you painted is what every
delivery — including interaction — reads.** It shipped as ref deliveries
(0.7, `roadmap/cell-ref`), which is why that release closed the CLI→TUI seam
rather than merely adding hyperlinks.

Reading B — the literal single function — is what the drive axis exists to
*avoid*. `run_cli` and `Surface` unify with `paint()` by *reading the same
four channels*, not by becoming arguments to it. The verb recurs and the
frameworks wear it (§5); one delivery path underlies all three drives (§6);
the channels carry through to every drive (this section). **"Never leave the
*verb* paint" is true and load-bearing; "never
leave the *function* `paint()`" is the overclaim the drive axis dissolves.**

**The door, named.** B is not incoherent — it is a ratification event that
can still be called, exactly as adding a fifth channel is. This document
records that as of 2026-07-04 the boundary holds (render channels × drive,
`run_cli` outside), and that reading A already delivers the unification B was
reaching for. Re-opening B means re-ratifying `design/paint-entry`'s
"`run_cli` does not fold in," with eyes open to the honesty-rule and
polymorphic-subject costs.

## 8. `paint()` has no `format`

Format leaves `paint()` entirely — it was never a rendering decision.

- **ANSI vs plain is detected, not declared.** It is a property of the
  destination: `file.isatty()`. `paint(x)` to a terminal renders ANSI; the
  same call piped, redirected, or aimed at a `StringIO` renders plain.
  Fidelity-to-terminal is a fact about the terminal, not a call-site kwarg.
- **Color-off is ambient.** `NO_COLOR` and a color/palette context govern
  it, exactly as `use_palette` / `use_icons` / `use_theme` already govern
  aesthetics. Forcing plain to a real TTY is an environment concern, not a
  parameter `paint()` carries. (`NO_COLOR` is wired into the color-depth
  layer in 0.8 — §11 Slice 1 — so this delegation is real, not aspirational;
  before 0.8 the section described an intent the code did not yet honour.)
- **JSON is not `paint()`'s concern at all.** JSON is *data emission*, not a
  rendering — `paint(x, format="json")` would mean "do not paint; serialize"
  a contradiction on a verb named `paint`. JSON lives at the harness:
  `run_cli --json`, which re-derives from the fetch data, not from the
  render (`runner.py`; `direction-p0s-audit`). This closes that audit's open
  tension — the JSON bypass was the correct position under the four-channel
  model, and now it has a principled home.

`run_cli` **keeps** `--json` / `--plain`: a *tool* legitimately declares its
output format as an argv axis, and the honesty rule earns those flags at the
harness altitude. The module verb does not declare format; it detects the
one axis that is a fact about the destination and reads the rest from
ambient context.

Consequence for the store: `design/paint-entry` said *"delivery params
(format, file) are where not what"* — it is now **`file` only**. Format is a
harness concern, struck from the module surface.

## 9. Migration and residue

`show()` becomes a **deprecated retained alias**, not a forwarder. A thin
forward to `paint()` is impossible — `paint()` has neither `format` nor the
`shape_lens`-*inferring* default, and those are exactly the two behaviours
`show()` must keep — so `show()` retains its pre-0.8 render body (inferring
default, ANSI detection, `Block`/scalar handling), but existing callers'
output is unchanged **except** two drifts, both accepted (2026-07-06) rather
than fenced off with a `paint()`-only branch — `show()` is removed at 1.0, so
propping up a dying alias's exact bytes for either isn't worth the seam:

- A **top-level `IntEnum`/`StrEnum`** previously hit the scalar
  short-circuit and rendered `str(value)` (`'ok'`, `'1'`); the Slice-2 scalar
  exclusion that routes a declared schema to the renderer now applies to
  `show()` too (it shares `paint()`'s render core), so it reaches the
  renderer and prints `Type.MEMBER` (`'Status.OK'`) instead. A bare (plain)
  `Enum` already rendered `Type.MEMBER` on 0.7 — `shape_lens` handled it —
  and is unaffected; nested `Enum`s of any flavor are unaffected too (the
  recursive path always dispatched through the same `Enum` branch).
- **Container dispatch now matches `(list, tuple)`, not `list` alone** — a
  shared spine change, not Enum-specific. `show((1, 'x'))` drifts from the
  `str()` fallback (`"(1, 'x')"`) to a dash-item list; a nested non-numeric
  tuple drifts the same way. Numeric tuples are unaffected — they always
  dispatched to `chart_lens` on `show()`'s inferring path.

On every call it emits `DeprecationWarning`, and it **narrows**:
`format` is dropped (`format="json"`/`"plain"` no longer honoured —
warn-and-narrow, the settled decision). `show()` has effectively no external
users (loops pins `<0.5`; siftd locks `0.4.0` with *zero* `show()` call-sites —
its boundary is `print_block` via `painted_bridge.py`), so dropping `format`
costs nothing. Removal lands at 1.0 with the `id→ref` aliases.

The residue sweep (`paint-entry`, research 2026-07-05) — the dissolution
rule requires it lands in the *same* change, not a follow-up:

| Surface | Scope (verified against the tree, 2026-07-06) |
|---|---|
| src | 4 files: `display.py`, `__init__.py` (`__all__` + lazy map), `core/zoom.py` (comment), `_doc_pages.py:577` (help text) |
| tests | ~56: `test_show.py` → `test_paint.py` (51), `test_fidelity_defaults.py` (4), `test_demo_liveness.py` (1 — the `'show'` primitive entry) |
| demos | ~24 real: `demos/primitives/show.py` → `paint.py` (15), `demos/patterns/rendering.py` (9). **Not 38** — the extra raw hits are `demos/primitives/span_line.py`'s *coincidental* local `def show(line)` (17), which is **not** the API and **must not** be swept |
| docs | ~15 across 6 files: ARCHITECTURE (1), FIDELITY (3), DIAGNOSTICS (3), DEMO_PATTERNS (1), **`PROFILING.md` (6 — runnable `from painted import show` examples)**, VOCABULARIES (1). REFS_DESIGN (2) and ERRORS (1) mention `show()` only as deprecation-horizon context and are **retained deliberately** — not flip scope |
| web | `walkthrough.astro` stage id `'show'` ×3 (+ the same section's `show(data) →` label text, incidental) |
| README | 4 (import, call, the `TODO` comment naming `show()`, the feature-table row) |
| consumer guide (`src/painted/CLAUDE.md` → symlink to README) | 7 |

Historical/dated docs under `docs/dev` (90 hits) are **exempt** — dated
artifacts are not swept. **Sweep by targeted edits, never a global
`s/show(/paint(/` substitution:** `span_line.py`'s local `show` helper and the
incidental English (`show cursor`, `showcase`) would be corrupted by a blind
replace — the counts above already exclude them.

**One consumer hazard.** loops' `apps/loops/cli/output.py` imports from
`painted.display` directly (the submodule path — it bypasses the lazy
`__getattr__` on the package root). The alias must therefore live in
`display.py` itself, not only in `__init__`. loops otherwise has ~40 sites
across 16 files, mostly function-scoped imports that migrate on its own
floor-bump schedule; siftd is zero-impact.

**Doc obligation** (`paint-entry`): teach the altitude story (§5) explicitly
where `paint()` is introduced — the recurring verb is the reason the name is
the keystone, and it is invisible if only the module call is shown.

## 10. Out of scope

- **The auto-lens question is answered, not deferred**: no lens ⇒
  transcription (§3). There is no "auto" default that guesses arrangement.
  `lens=shape_lens` remains available as explicit exploration.
- **`run_cli`'s optional `render=`** (the no-lens graduate, §2) is a
  trigger-gated lane on the evolving `cli` surface — recorded there, built
  when the first no-lens graduate arrives. Built as of 0.11: see the §2
  amendment — the seam is `renderer=`'s transcription default, not `render=`
  turned optional.
- **`format`/JSON reshaping at the harness** is not touched here — `run_cli`
  keeps its flags as they are (§8). The `to_markdown` emitter and promoting
  `to_html` to the library surface stay their own trigger-gated lanes
  (`direction-p0s-audit`).
- **Mark persistence** (`roadmap/mark-persistence`) is a separate lane; it
  will make the mark channel survive into artifacts the way ref does, and it
  reuses the per-cell annotation shape 0.7 established — but it is not part
  of the `paint()` entry work.
- **The TUI event contract, keymap grammar, and batteries** ride 1.x on the
  evolving `tui/` surface; 1.0 is the semantic-static core and is not
  hostage to them.

## 11. Implementation plan

Four slices, sequenced so the *name* exists before behavior narrows, the
*behavior* settles before docs describe it, and the residue sweep lands with
the reconcile in one cut (the dissolution rule — §9). Process mirrors 0.7 ref
deliveries (`roadmap/cell-ref`): per-slice review fan-out + adversarial
verify per finding, a full-diff read, and a release-focused cross-family
review at the cut; the 10-tier gate green at every commit.

The code surface is smaller than the design's reach, because three pieces
already exist: `Block.paint` is the buffer altitude (§5) — no work, only the
altitude story to document; `print_block` is already the plumbing `show()`
delegates to (§6) — the subsumption is inherited, not built; and `show()`'s
`Block` passthrough (`display.py:70–79`) already makes `paint(Block)` work.
The real code is the *name + alias*, and the *transcription* front-door.

### Slice 1 — `paint()` + `show()` deprecated alias (core)

Files: `src/painted/display.py`, `src/painted/__init__.py`, new
`tests/unit/test_paint.py`.

- Add `paint(subject, *, zoom=None, lens=None, file=None)` — the final
  signature, **no `format`**. Body is `show()`'s render logic minus the
  format/JSON branches, with one detection fix: ANSI is decided from the
  **resolved `file`** (`file.isatty()`), *not* `sys.stdout`. The inherited
  `_detect_show_context` reads `sys.stdout` and ignores `file`, so
  `paint(x, file=StringIO())` from a TTY would wrongly emit ANSI — §8 makes
  `file.isatty()` the contract, so `paint()` fixes detection to honour it
  (add a regression test: `paint(x, file=StringIO())` is plain). Then
  `Block` → `print_block`; scalar → `str`; else render through the lens.
- `show()` becomes the deprecated **retained alias in `display.py` itself** —
  the loops `painted.display` submodule-import hazard (§9) means the alias
  cannot live only in `__init__`. It keeps its pre-0.8 render body (inferring
  default, ANSI detection, `Block`/scalar) so existing output is unchanged,
  emits `DeprecationWarning` on every call, and **narrows** — `format` is no
  longer honoured (warn-and-narrow: keep the param, warn, ignore; ~zero
  users). It is *not* a forward to `paint()` (which lacks both `format` and
  the inferring default). `show()` keeps the inherited `sys.stdout`-based
  detection (bug-compatible); only `paint()` gets the `file`-aware fix above.
  Removal at 1.0, one horizon with `id→ref`.
- `__init__.py`: add `"paint"` to `__all__` and `_LAZY_IMPORTS`
  (`"paint": (".display", "paint")`); `show` stays exported (deprecated).
- **NO_COLOR** (§8, Q4): wire `NO_COLOR` into the color-depth resolution
  (writer layer) so color-off is genuinely ambient — env var present ⇒ plain,
  honoured by both `paint()` and `run_cli`. Writer-layer, standalone; makes
  §8's delegation real. (Touches the writer, not just `display.py`.)
- **Two decisions, settled** (2026-07-06): (a) `paint()` **keeps** the no-arg
  blank-line `print()` affordance (`display.py:61–64`) — the sole arity
  concession; the closure law governs kwargs, not arity, so a bare `paint()`
  does not breach it. (b) the `show()` alias **drops `format`**
  (warn-and-narrow) — `format="json"`/`"plain"` are no longer honoured.
- Behavior-preserving for `paint(Block)`/scalars; the transcription change is
  deliberately **not** here.

### Slice 2 — the transcription front door

Files: `src/painted/display.py` (the `render_fn = lens or shape_lens`
default, `display.py:99–101`), plus the transcription renderer's home.

- With **no lens**, `paint()` transcribes the *declared shape* (§3, **wide**):
  mapping → key/value, sequence → items, **`dataclass`/`NamedTuple` → their
  declared fields, `Enum` → `Type.MEMBER`**. `shape_lens` (the *inferring*
  renderer) becomes explicit opt-in (`lens=shape_lens`). Scalars already
  transcribe (`display.py:91–95`) — unchanged. This is the one real behavior
  change vs `show()` (§3); the `show()` alias keeps `shape_lens` as *its*
  default, so old behavior is preserved behind the deprecation.
- **Approach: HYBRID** (settled after reading `shape.py`). Inference is *not*
  a liftable "non-numeric branch" — it is interleaved into `_shape_lens` at
  three stanzas (dict→chart, dict→tree, numeric-seq→chart) *and* the container
  helpers recurse by calling `_shape_lens` **by name** (`_render_dict`
  273/303, `_render_list` 370). So: (1) **reuse** the five render bodies
  (`_render_dict`, `_render_list`, `_render_set`, `_render_scalar`,
  `_render_enum`) unchanged — they already transcribe, none infers; (2)
  **fork the spine** — a transcription worker = `_shape_lens` minus the three
  inference stanzas, *keeping* the `dataclass`/`NamedTuple`/`Enum` branches
  (wide); (3) **parameterize the recursion seam** — the container helpers must
  recurse through an injected child-renderer, not the hardcoded `_shape_lens`,
  so transcription recurses *as* transcription (**recursive** — no chart at
  any depth). A fork + one seam, not new render code: it dissolves to a
  composition of what exists (§3) minus the inference, plus a recursion seam.
- **Dissolution residue:** the fork orphans inference-only predicates —
  `_is_labeled_numeric` / `_is_hierarchical` are *already* dead (defined,
  uncalled); sweep them in this cut. `_is_numeric_sequence` stays (still used
  by the `shape_lens` inferring path).
- Tests: `paint(dict)`→kv; `paint([1,2,3])`→items, **not** a chart;
  `paint(Server(...))`→field table (wide); `paint({"xs":[1,2,3]})`→nested
  items, **not** a chart (recursive); `paint([1,2,3], lens=chart_lens)`→chart;
  `paint(x, lens=shape_lens)`→the old inferring behavior intact.

### Slice 3 — the residue sweep (dissolution)

The §9 table, landed in this cut, not deferred:

- Rename `tests/unit/test_show.py` → `test_paint.py`; `demos/primitives/show.py`
  → `paint.py` (update `demos/CLAUDE.md`, the outputgen manifest if it names
  the demo).
- Flip docs per the corrected §9 table — ARCHITECTURE, FIDELITY, DIAGNOSTICS,
  DEMO_PATTERNS, **`PROFILING.md` (runnable examples)**, VOCABULARIES —
  README ×4, `src/painted/CLAUDE.md` (→README) ×7, `web/walkthrough.astro`
  stage id `'show'` ×3, then `./dev panels` to regenerate any panel that
  renders the old name (the `outputgen` gate will catch drift). REFS_DESIGN
  and ERRORS keep their `show()` deprecation-horizon mentions — **retained
  deliberately, not flip scope** (§9). **Targeted edits only — no global
  `s/show(/paint(/`** (the `span_line.py` collision, §9).
- **Doc obligation** (§5, `paint-entry`): where `paint()` is introduced —
  consumer-guide Level 0, README hero, `PRIMITIVES.md` — teach the altitude
  story (module→buffer, the recurring verb), not just the module call.
- `docs/dev` historical (90 hits) stays **exempt**.

### Slice 4 — reconcile + cut

- `PAINT_DESIGN.md` status PLANNED → IMPLEMENTED; add it to the root
  CLAUDE.md docs register.
- CHANGELOG `0.8.0` entry; `pyproject.toml` `0.7.0` → `0.8.0`.
- Amend the store: `design/paint-entry`'s "delivery params (format, file)"
  → **`file` only** (§8); record the transcription amendment (**wide +
  recursive**) to its "`show()` is 80% there" framing and the four settled
  decisions (no-arg kept, `show()` warn-and-narrow, NO_COLOR built); flip the
  `paint-entry` roadmap node pending → built.

### Consumer coordination

No cross-repo blocking. loops (`<0.5`) and siftd (`0.4.0`) are behind 0.5.1
already and floor-bump on their own schedule; the `display.py`-resident alias
(Slice 1) covers loops' direct-submodule import in the meantime; siftd is
zero-impact.

### Settled before build (2026-07-06)

Four decisions, ratified with worked examples: **(1) transcription recurses**
(never infer at any depth); **(2) wide** — `paint()` transcribes stdlib
declared shapes (`dataclass`/`NamedTuple`/`Enum`) as their fields, third-party
(pydantic/attrs) deferred; **(3) `show()` warn-and-narrow** — retained body,
warns, drops `format`; **(4) NO_COLOR built** in 0.8. The `shape.py` read
resolved the renderer approach to **HYBRID** (Slice 2). The reorientation
scout also corrected the §9 residue counts, found the `file.isatty()`
detection bug (fixed in Slice 1), and flagged the `span_line.py` sweep hazard
(Slice 3).
