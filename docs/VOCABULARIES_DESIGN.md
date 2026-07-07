# Declared vocabularies — the mark channel and the color contract

**Status: RATIFIED** (design discussion 2026-07-04; store:
`sl read project decision/design/declared-vocabularies` and
`roadmap/vocabularies-doc`). **Build sequence items 1–3 implemented 2026-07-05**
(the 0.6 arc, branch `declared-vocabularies`); items 4–5 ride the 0.8 paint()
release and the consumers' own schedules. This is the design of record for the fourth
meaning channel (**mark**) and for the rule that every color in a painted
program traces to a declaration. Companion to `docs/FIDELITY_DESIGN.md` —
that document gave *disclosure* its declaration grammar; this one does the
same for *classification*. It is the first document in the paint-1.0 arc:
`CELL_REF` (denotation), `paint()` (the entry point), and the TUI event
contract all instantiate or consume the pattern defined here.

## 1. The contract

`paint()`'s meaning vocabulary is **closed at the channel level and open at
the value level**. Four channels:

| Channel | Kwarg | What it declares | Vocabulary |
|---------|-------|------------------|------------|
| disclosure | `zoom=` | how much to show | painted's (the zoom ladder) |
| arrangement | `lens=` | how to structure it | painted's (lens contract) |
| denotation | `ref=` | what it refers to | **app's** (ref schemes) |
| mark | `mark=` | where it stands | **app's** (declared vocabularies) |

Adding a channel is a ratification event, not an API addition. Two channels
take app-open vocabularies; painted owns the *mechanism* — declaration,
validation, generation, consistent rendering in every delivery — and never
the app's words.

A **vocabulary** is a closed set of named values requiring consistent
treatment. Order is an optional property, not the price of admission:

- **Unordered** (the common case): fact kinds, edge direction (`in`/`out`),
  origin (`native`/`discord`). Base guarantee only: same value → same
  treatment, in every delivery, at every call site.
- **Ordered**: severity, freshness, priority, lifecycle. Declaration order
  *is* the order. Unlocks the comparative behaviors: thresholds, `at_least`
  gating, gutter escalation, "which end pulls attention."
- No partial orders. A lifecycle that forks at the end
  (`queued → running → succeeded|failed`) is either declared unordered or
  split into two vocabularies. The property is binary.
- A vocabulary of one is legal — "this thing gets treated like this" is a
  complete declaration.

**Severity is not a channel.** It is the built-in ordered vocabulary inside
mark — the depth-vs-Tag pattern repeating: depth is the anonymous built-in
disclosure axis and Tags extend it; severity is the built-in mark vocabulary
and declared vocabularies extend it.

**The color contract**: every `Style` a renderer applies for *meaning*
traces to a role, and every role traces to a declaration — painted's five
core roles (painted's own declaration), an app-declared role carried by a
vocabulary, or the `series` ramp. A hex code in a call site is presentation
from nowhere; the mechanism makes it unnecessary.

**The boundary with `series`**: vocabularies are closed and declared;
`series` is for open, dynamic sets (chart lines, experiment arms, observers
arriving at runtime). The test is decidable: can the app enumerate the
values at declaration time? Open sets get deterministic ramp assignment
(§5); they never enter a vocabulary by force.

**The honesty rules** (each testable):

1. A declared vocabulary must change output — declaring `freshness` and
   never marking with it is a contract violation.
2. An undeclared lookup raises at the seam — `mark=("freshness", ...)`
   without a `freshness` declaration is a construction error, not a silent
   `muted` fall-through. (Precedent: `callout()` raises on an unmapped
   Severity; `check_declarations` raises at parser construction.)
3. A value outside the vocabulary raises, unless the vocabulary declares
   `overflow` (§5). No invented candidates.
4. Vocabularies generate **no CLI flags**. A mark classifies data; it is not
   user grammar. (Contrast Tags, which exist to *become* flags.)

## 2. Why (the evidence trail, compressed)

Surveyed 2026-07-05: painted's internals, siftd, and the loops monorepo
(loops CLI, strange-loops/tasks, hlab). Full inventory in the store
(`roadmap/vocabularies-doc`).

1. **Severity is never abused — it is bypassed.** One correct use in the
   entire loops monorepo (`store.py` chain verification). Everything else
   built parallel systems, because none of these vocabularies fit a closed
   4-value enum: at least **14 hand-rolled vocabularies** across three apps
   (kind taxonomy, tier/rail, freshness, observer identity, task status,
   "is-closed" sets, emit receipt roles, horizon proximity, media audit
   status, alert severity, container health, experiment status, idea/
   hypothesis status, hlab's own 4-role theme).
2. **The drift is measurable, not hypothetical.**
   `loops/commands/emit.py:117` maps `"warn"` to `p.error` — a warning
   renders as an error. hlab colors log sources with builtin `hash()`
   (PYTHONHASHSEED-randomized: same source, different color per process)
   while loops' `observer_style` independently landed on md5 — two builds of
   the same pattern, one correct. `tasks/dashboard.py` and `tasks/store.py`
   disagree on the unmatched-status fallback (`muted` vs `accent`) and both
   carry `# TODO: needs its own semantic token` for `"exhausted"`. The tier
   vocabulary lives in three files, hand-synced. A dead
   `RESOLVED_STATUSES` frozenset shadows a live, narrower `_CLOSED_STATUSES`.
3. **painted has the disease internally.**
   `views/record.py:718-759` — `gutter_lifecycle`, `gutter_freshness`,
   `gutter_pass_fail` are three hardcoded string→role mappings, each
   inventing its own status set. `diagnostics.py:60` redeclares
   `_callout.py`'s severity→role map instead of sharing it.
4. **The consumers named the fix before painted did.** loops'
   `observer_style` comment: *"aliased over the kind hash pool for now...
   once declared Peers give observers a typed face."* The loops TUI concept
   mockup hand-rolled `freshGood`/`freshMid`/`freshOld` theme roles — a
   scale→role mapping invented under pressure.

Same shape as the fidelity evidence (three generations re-deriving
flag-parsing): a dissolution seam announcing itself.

## 3. The declaration

Two frozen types and one ambient seam. Neither existing seam fits alone —
the ContextVar seam (`use_palette`) validates nothing; the CLI seam
(`Tag`/`check_declarations`) never leaves `cli/` and compiles to booleans.
Vocabularies are the hybrid: **Seam-B validation at declaration time,
Seam-A ambient reads at render time** — painted's first compiled ambient
vocabulary.

```python
from painted import Role, Vocabulary, use_vocabularies

FRESHNESS = Vocabulary(
    "freshness",
    values=("fresh", "recent", "stale", "old"),
    ordered=True,                      # declaration order IS the order
    roles={
        "fresh":  "accent",                            # core role by name
        "recent": "text",
        "stale":  Role("stale", Style(fg="bright_yellow")),  # inline-declared
        "old":    "muted",
    },
)

KIND = Vocabulary(
    "kind",
    values=("decision", "thread", "task", "friction", "hypothesis",
            "observation", "session", "change", "log"),
    roles={"decision": "accent", "task": "success", "thread": "warning",
           # ... every value bound; unbound value = construction error
           },
    overflow="series",                 # unknown kinds fall to the ramp (§5)
)

use_vocabularies(FRESHNESS, KIND)      # ambient; also a context manager
```

- **`Vocabulary(name, values, *, ordered=False, roles, overflow=None,
  attention="last")`** — frozen. Validation at construction (the
  `check_declarations` discipline): kebab-case names, unique values, every
  value bound to a role, role references resolvable. `attention` names which
  end of an ordered vocabulary pulls the eye (severity: `error` end;
  meaningful only when `ordered=True`).
- **`Role(name, style)`** — an app-declared role joining painted's five. A
  role is declared exactly once (inline, by the first vocabulary that needs
  it); redeclaration under the same name with a different style raises.
  Referenced by name everywhere else. Palettes and themes may override any
  declared role by name (`Theme(roles={"stale": Style(...)})`), so app roles
  theme exactly like core roles — declaring the role is what makes the value
  *themeable* rather than hardcoded.
- **`use_vocabularies(*vocabs)`** — same dual-mode shape as `use_palette`:
  immediate ambient set, scoped override when used as a context manager.
  Name collisions across active vocabularies raise at the call.
- **Thread safety** — same rule as palettes: ContextVar state does not cross
  threads. Long-lived handlers snapshot at construction and reapply per-emit
  (the `PaintedHandler` precedent, `diagnostics.py:142-169`).

## 4. Consumption

One resolution mechanism, used at every grain:

```python
from painted import mark_style, paint

# entry point — whole-datum marking
paint(record, mark=("freshness", "stale"))
paint("migration failed", mark="error")       # bare value → built-in severity

# lens internals — per-field, same declaration
style = mark_style("kind", item.kind)          # -> Style, via current palette
rail  = mark_style("freshness", bucket(item.age))

# ordered behaviors
FRESHNESS.index("stale")                       # 2
FRESHNESS.at_least("stale")                    # ("stale", "old")
if FRESHNESS.cmp(value, "stale") >= 0: ...     # ordered comparison
```

- `mark_style(vocab_name, value)` resolves value → role → `Style` through
  the *current palette* (palette/theme override first, declared default
  second). This is the single point meaning becomes color — the analogue of
  `fidelity.shows()`.
- `paint(x, mark=...)` takes a `(vocabulary, value)` tuple; a bare string is
  shorthand into the built-in severity vocabulary only. Explicit over
  implicit: no search across declared vocabularies for a bare value.
- **Thresholds** generalize `DEFAULT_THRESHOLDS`: a mapping from a numeric
  domain onto an ordered vocabulary's values
  (`Thresholds(FRESHNESS, {600: "fresh", 3600: "recent", 86400: "stale"})`,
  greatest floor cleared wins — the `_resolve_severity` algorithm, promoted).
  loops' freshness seconds, hlab's horizon ratios, and logging's levelnos are
  all instances.
- **Gutters** consume vocabularies instead of owning them: the
  `record_line` gutter factories take `(vocabulary, payload_field)` and
  derive glyph weight from `attention`-relative position. The three
  hardcoded gutter functions become thin declarations (§7).

## 5. Open sets — sticky series and overflow

Open, dynamic sets get deterministic ramp assignment, factored from the
prototype that already exists (`flame_lens`'s hash-into-ramp;
`palette.py:47` — "the general form a reusable ramp helper would factor
out, once a second consumer exists" — observers are the second consumer):

```python
current_palette().series_for(key)   # deterministic: digest(key) % len(series)
```

- **Deterministic digest (md5 of the key), never builtin `hash()`** —
  PYTHONHASHSEED randomizes `hash()` per process; hlab's log-source coloring
  has this bug today, loops' md5 `observer_style` is the correct prior art.
  Same key, same color, every process, every session.
- `flame_lens` keeps its adjacent-sibling avoidance locally (a flame-shaped
  concern), rebased onto `series_for`.
- **Observers/workers default**: no declaration needed — `series_for(name)`.
  Stable identity color for an open set, zero ceremony.
- **The upgrade path**: `Vocabulary(..., overflow="series")` — declared
  members get their bound roles; unknown members fall to the ramp instead of
  raising. This is the middle ground for sets that are *mostly* closed
  (loops' kind taxonomy today: 9 declared kinds + a hash pool fallback —
  exactly this shape, hand-built).

## 6. Ref schemes — the sibling declaration

*(Implemented 2026-07-05 in the 0.7 ref-deliveries arc —
`docs/REFS_DESIGN.md` is the design of record for the built form:
`painted.refs`, the `resolve_ref` choke point, and the OSC 8 / HTML
readers.)*

The denotation channel's vocabulary is the **ref scheme**: how an opaque
ref (`"fact:01JQ8F…"`) resolves for deliveries that can express it.

```python
from painted import RefScheme, use_refs

use_refs(RefScheme("fact", lambda id: f"https://loops.dev/f/{id}"))
```

- Resolution only: `scheme → (ref) → URI | None`. No styling — link *color*
  is the delivery's concern; a ref that also wants categorical color (edge
  in/out) is carrying an ordinary vocabulary mark alongside its ref, not a
  ref-scheme feature.
- Honesty: no declared scheme → refs stay inert in every delivery. painted
  never invents URIs. (Consumed by the OSC 8 / HTML work — see the cell-ref
  roadmap node; the declaration lives here because it is the same pattern.)
- Same ambient seam, same validation discipline, same thread-safety rule.

The fourth instantiation of the pattern — keymaps (`{key: action}`
declarations generating help/status lines) — belongs to the TUI release and
is specified there. This document defines the pattern once: **declare →
validate at construction → generate → honesty rule.** Tags were the first
instance, completion the second, vocabularies + ref schemes the third,
keymaps the fourth.

## 7. The built-in vocabulary, and remediation

- `Severity` (the enum) survives unchanged as the typed spelling of the
  built-in vocabulary — semver-stable, still closed, still raising on
  unmapped members. Internally, `_callout.py`'s `_SEVERITY` role-half and
  `diagnostics.py`'s `_SEVERITY_ROLE` (formerly independent duplicates)
  collapsed into the one built-in `Vocabulary("severity", ...)` declaration.
  `DEFAULT_THRESHOLDS` is re-expressed as a `Thresholds` onto it — public
  shape unchanged. (One deliberate delta: a record below every declared
  floor now resolves to the smallest floor's value, not a hardcoded INFO —
  identical under `DEFAULT_THRESHOLDS`; diagnostics had not shipped.)
- `views/record.py`'s `gutter_lifecycle` / `gutter_freshness` /
  `gutter_pass_fail` were the internal remediation targets: each is now an
  ordered example vocabulary + a `record_gutter` factory call, and their
  status sets stopped being three private dialects (raw payload spellings
  became explicit aliases). They were also the acceptance test: if the
  mechanism couldn't express painted's own gutters more simply than the
  if-chains, the mechanism was wrong. It passed — glyph weight derives from
  distance-to-the-attention-end against a ramp, so the fade rail (freshness)
  and the escalation rails (lifecycle, pass-fail) are one rule with two
  ramps, not two code paths. The example vocabularies are deliberately NOT
  registered as built-ins: a consumer's own `freshness`/`lifecycle`
  declaration must never collide with a painted example. One boundary drawn
  in the build: honesty rules govern *declarations*; a gutter renders
  *data*, so out-of-vocabulary payload values route to a declared `unknown`
  fallback rather than raising — a rail never raises on data.
- Downstream (consumer guidance, their schedule): `LoopsPalette` dissolves
  into declarations — kind taxonomy → `Vocabulary` with `overflow="series"`,
  freshness → ordered vocabulary + `Thresholds`, tier → one vocabulary
  replacing three hand-synced maps, observer → `series_for`. hlab's `Theme`
  roles → declared roles; its hash bug disappears by construction. The
  `emit.py` warn→error bug becomes unwritable: `mark="warn"` either resolves
  through the declared binding or raises.

## 8. What this is not

- **Not markup.** No `[stale]…[/]` strings, ever. The vocabulary is declared
  once; values arrive as data.
- **Not per-datum styling.** `paint()` gains no `style=` kwarg. If a color
  has no declared meaning behind it, painted does not have a channel for it
  — that is the position, not a gap.
- **Not flags.** Vocabularies never generate CLI surface (§1, rule 4).
- **Not a theme system.** Roles remain the presentation half; palettes and
  themes own what roles look like. Vocabularies own only which role a value
  *means*.

## 9. Open questions

1. **Multiple marks per datum.** A record can be both `stale` and
   `blocked`. `paint()` takes one mark (the primary stance); lenses resolve
   the rest per-field via `mark_style`. Sufficient until a consumer needs
   compound marking at the entry point — revisit then.
2. **Kwarg name.** `mark=` (chosen: short, verb-adjacent, pairs with
   "marker"). Alternative considered: `standing=` — rejected as naming only
   the ordered case.
3. **Per-preset role overrides in presets painted ships.** Should
   `NORD_PALETTE` know about app roles? No — apps override via
   `Theme(roles=...)`; shipped presets stay app-agnostic.
4. **String shorthand `"freshness:stale"`.** Deferred; the tuple is the
   declared form. Revisit if a CLI/config surface needs a flat spelling.

## 10. Build sequence

1. **DONE (89fcddc)** — `Role`, `Vocabulary`, `Thresholds`,
   `use_vocabularies`, `mark_style`, `Palette.series_for` (+ md5 digest
   helper). Unit + property tests pin the honesty rules (§1) and
   determinism (§5). The registry grew two layers in the build (built-in +
   app) so the severity declaration of item 2 cannot be wiped by an app's
   `use_vocabularies`; `Theme` grew `roles=` as the override path.
2. **DONE (7b3b919)** — Severity reframe: single built-in declaration;
   `_callout` + `diagnostics` consume it; `DEFAULT_THRESHOLDS`
   re-expressed. No public surface change.
3. **DONE (c1e40ab)** — Internal remediation: `record.py` gutter functions
   re-expressed via the mechanism (the acceptance test — passed; see §7).
   `record_gutter` joined the stable views surface.
4. `paint(mark=)` lands with the paint() entry-point work (separate
   release; this mechanism ships first, so callers can consume
   `mark_style` immediately — before the `paint(mark=)` sugar).
5. Consumer migration guidance (loops/hlab/tasks) — their schedule, with
   the §7 dissolution map as the offer.
