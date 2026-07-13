# Fidelity — the disclosure grammar and the consumption ladder

**Status: RATIFIED + IMPLEMENTED 2026-06-10** (branch `fidelity-grammar`).
The §7 questions are settled — (a) accepted into §4, the rest deferred or
declined as recommended. The grammar, both behavior breaks (budgets opt-in,
`Depth` removal), the docs-CLI migration, and the teaching reform are built;
`tests/unit/test_tag_grammar.py` pins the compilation laws and the §6
acceptance tables. Known residue beyond §6's list: siftd's `-b`/`-F` *short*
spellings — `depth_aliases` generates long flags only (open call). This
document is the design of record. Companion to
`docs/LIVE_DELIVERY_DESIGN.md` — that document gave the *delivery* axis its
contract; this one does the same for *disclosure*.

## 1. The contract

`run_cli` has two axes: how output reaches the terminal (delivery) and how
much output there is (disclosure). Delivery got the full treatment — a
graduation ladder (`paint` → `run_cli` → `--live` → Surface), a declared
capability surface (`modes=` filters which of `-i`/`--live`/`--static` exist),
and the invariant that climbing a rung never rewrites the rung below.
Disclosure got the spec (`Fidelity`) but no ladder, no declaration grammar,
and no honesty rule. This design extends the ratified delivery principles to
the disclosure axis. **The tag grammar is `modes=`, generalized.**

The disclosure ladder, each rung additive:

| Rung | You need | You write | The framework provides |
|------|----------|-----------|------------------------|
| 0 | decent defaults | `paint(data)` | sensible disclosure, no ctx at all |
| 1 | detail levels | `if ctx.zoom >= Zoom.DETAILED:` | `-q`/`-v`/`-vv`, free |
| 2 | a semantic layer | declare a `Tag`; gate with `ctx.fidelity.shows("thinking")` | the `--thinking` flag, help text, depth implication |
| 3 | density control | declare budget support; read `fidelity.chars`/`lines` | `--max-chars`/`--max-lines`, only now |
| 4 | structural disclosure | build a `Doc`; `doc_lens` applies the whole spec | branching disappears entirely |

One job per name:

- **Flags** (`-v`, `--thinking`, `--max-lines`) are the *user's* grammar.
- **`Fidelity`** is the *compiled spec* — what the grammar compiles into.
  "Canonical" means *compilation target*, not "what you must consume."
- **`Zoom`** is the rung-1 *view* of the spec — not a backward-compat shim
  but the honest name for the first axis, blessed permanently. `ctx.zoom` is
  a porthole onto `ctx.fidelity`; day-one code that reads it stays
  load-bearing forever.
- **`run_cli`** is the *compiler*; the app's declarations (tags, budgets,
  modes) are its configuration.
- **`Depth = Zoom` dies.** "Either name is fine" was the indecision; the
  ladder is the decision.

Two contract rules:

- **The spec travels whole.** Renderers that consume beyond rung 1 receive
  `Fidelity` intact (`ctx.fidelity`, lens `fidelity=`), never exploded into
  kwargs. (Evidence: siftd passes it whole and reads clean; loops explodes it
  with a silent `TypeError` fallback and reads like an apology — §2.)
- **The honesty rule.** A flag exists only because a capability was declared,
  and a declared capability must change output. Undeclared → no flag (so dead
  flags are structurally impossible); declared-but-ignored is a contract
  violation, testable per app (render with and without the tag, assert the
  output differs).

## 2. Why (the evidence trail, compressed)

Surveyed 2026-06-10: painted's demos/internals, siftd (`~/Code/siftd`), and
the loops monorepo (`~/Code/loops`: loops CLI, strange-loops/tasks, hlab).

1. **Three generations re-derived flag→Fidelity parsing.** painted's
   `parse_fidelity`, siftd's `cli/_common.py:fidelity_from_args`, loops'
   `cli/fidelity.py:fidelity_from_args`. The loops docstring is explicit:
   *"Mirrors siftd's ``cli/_common.py:fidelity_from_args``: pure, narrow,
   testable"* — a convention consciously maintained across repos by hand
   because the framework doesn't own it. Same signature as the multi-format
   envelope P0 ("two generations re-derived it"): a dissolution seam
   announcing itself.
2. **`Fidelity.visible` is field-validated, twice independently.** siftd:
   `--thinking`/`--tools` gated via `fidelity.shows()` in its narrative
   walker. loops: `--facts`/`--refs` → tags consumed in `fold.py`. doc-IR:
   `--show rationale`. Two unrelated domains needed disclosure orthogonal to
   depth and reached for the same mechanism. The model is proven; the
   *delivery* of the model is what everyone routed around — painted's flag
   surface can only produce depth, so the moment an app needs `--thinking`
   it exits the framework and takes flag parsing with it.
3. **Apps were forced to be framework authors.** loops carries its own
   parser, its own dispatch conversion (`Fidelity` → zoom + exploded
   kwargs), and its own lens-calling convention (`call_lens` silently falls
   back to 3 params, dropping tags/budgets on the floor). Every loops lens
   inherits an undocumented variadic contract.
4. **Budgets parse but don't render, everywhere.** `--max-chars`/`--max-lines`
   are added unconditionally by `add_cli_args`; 13+ loops lenses ignore them,
   siftd never reads `fidelity.lines`, siftd's `export --tools` is a dead
   flag, and no painted demo honors them. The universal dead-flag is the
   class of bug the honesty rule closes.
5. **The consumer tiers already form the ladder.** tasks consumes scalar
   `ctx.zoom` via `run_cli`, happily. hlab consumes scalar zoom plus its own
   Theme axis. loops and siftd consume the full spec. Nobody is wrong;
   they're at different rungs — the design's job is to make moving between
   rungs additive instead of an exodus.
6. **Idiom verdict from the field.** Mature consumers converged on `>=`
   thresholds (siftd ~20 sites, loops' incremental gates, `record_line`).
   The `==` equality ladders are copy-paste descendants of painted's own
   demos. Nobody invented a declarative consumption idiom despite ample
   motivation — what they invented, unanimously, was *parsing*. So the
   grammar is the centerpiece; `>=` is blessed; no declarative idiom is
   imposed on hand-built renders (rung 4 exists for structure).

## 3. What already exists

- `Fidelity` (`core/fidelity.py`) — the spec: depth / visible / chars /
  lines. **No field changes in this design.** Compilation resolves flags and
  implications *into* the spec; consumers just read it.
- `add_cli_args(parser, modes=...)` (`cli/types.py`) — the capability-filtered
  flag surface, already ratified for the delivery axis. The precedent this
  design generalizes.
- `run_cli(add_args=..., build_fidelity=...)` hooks — today's escape hatch;
  exactly what `_docs_cli.py` uses to bolt on `--show`. The grammar is the
  dissolution of this pair for the common case; the hooks remain as the
  rung below it for app-specific residue (siftd's `--tool-chars`, loops'
  int-valued `--refs N`).
- `help_args=[HelpArg(...)]` + zoom-aware `help_doc` — declared args already
  feed rendered help; tag/budget declarations feed the same path, so a
  declaration buys flag + parse + help in one move.
- `fidelity.shows(tag)` / doc-IR's tagged nodes — the consumption surface for
  tags, unchanged.
- The field's parsers (`siftd/cli/_common.py`, `loops/cli/fidelity.py`) —
  the acceptance fixtures. See §6.

## 4. The design

### The declaration

```python
@dataclass(frozen=True)
class Tag:
    name: str               # the noun; generates --{name}
    help: str               # one-line help text
    implied_at: int | None = None   # depth at which the tag turns on implicitly
```

Lives in `cli/types.py` beside the parsing it configures (spec in core,
grammar in cli — the existing layering). Exported from `painted.cli` and the
top-level `painted` namespace. The evolving-framework surface, not the
semver-stable one.

### The grammar, at two altitudes

**Knob altitude** — `run_cli` / `CliRunner` (and `AppCommand` per-command):

```python
run_cli(
    argv,
    renderer=renderer,
    fetch=fetch,
    tags=[
        Tag("thinking", "Show model reasoning", implied_at=3),
        Tag("tools", "Show tool calls and results", implied_at=3),
    ],
    budgets=True,           # opt-in: only now do --max-chars/--max-lines exist
)
```

**Function altitude** — for custom harnesses (siftd's multi-command CLI,
loops' dispatch) that will never adopt `run_cli` wholesale:

```python
add_cli_args(parser, modes=..., tags=SIFTD_TAGS, budgets=False)
fidelity = parse_fidelity(parsed, zoom, tags=SIFTD_TAGS)
```

**Depth aliases** — app-local spellings for depth levels, at both altitudes:

```python
depth_aliases={"brief": 0, "full": 3}   # generates --brief / --full
```

Pure spelling: an alias flag sets depth (mutually exclusive with `-q`/`-v`,
same argparse group), then compilation proceeds identically — so siftd's
`--full` is `depth=3`, which trips the `implied_at=3` tags. One dict, no new
concepts; exists because without it siftd keeps a parser and §6's
deletability test fails.

The functions are the rung below the knob — the knob is implemented *as*
them. This is what makes downstream parsers deletable (§6) without forcing a
harness migration, and it is itself monotonic: adopt the functions today,
graduate to the knob if/when the harness dissolves.

### Compilation rules

- Each `Tag` generates `--{name}` (`store_true`), grouped under a "Layers"
  section in argparse and in the rendered help doc.
- `fidelity.visible` = tags whose flag was passed ∪ tags whose
  `implied_at is not None and depth >= implied_at`. Implications resolve at
  compile time — the spec stays dumb, consumers just call `shows()`.
- **Collision check**: a declared name — tag or depth alias — that collides
  with a framework flag (`live`, `static`, `json`, `plain`, `max-chars`, …)
  or another declaration (tag↔tag, tag↔alias) raises at parser construction,
  not at runtime. Declarations are checked because they are promises.
- `budgets=False` (default): `--max-chars`/`--max-lines` are **not** added.
  This changes today's behavior — the flags are currently unconditional —
  which is the honesty rule applied retroactively: no current `run_cli` app
  honors them (tasks' lenses are 3-param; demos hand-build). Pre-0.2.0 is
  the window for this break.
- `build_fidelity` still runs last, after tag compilation — the escape hatch
  ordering is unchanged.

### Vocabulary deaths and demotions

- `Depth = Zoom` alias: removed. (`Depth` is exported via `painted.__init__`
  and `cli/types.__all__`; `core` removals are semver-MAJOR by policy —
  pre-0.2.0 is the window. No internal consumer uses it.)
- `CliContext.zoom` docstring: from "backward-compat" to "the rung-1 view of
  the spec." The `min(depth, 3)` clamp stays (depth is an open int in the
  spec; the porthole is bounded by the enum) and is now documented as such.
- `core/fidelity.py` docstring: "three-axis" → honest field list (depth,
  visible, density×2), with the ladder vocabulary.
- The consumer guide (`src/painted/CLAUDE.md` Level 2): "Three orthogonal
  dimensions" section rewritten as the disclosure ladder; `--show` examples
  replaced with `Tag` declarations.

### Teaching reform (the demos are the documentation)

- The 18 pattern demos' `== Zoom.X` ladders convert to `>=` thresholds —
  the idiom the mature consumers converged on, taught at the source the
  copy-paste descends from.
- One demo becomes the rung-2 exemplar: `raymarch.py` declares
  `Tag("stats", "Show march internals", implied_at=3)` — its FULL-only
  stats block is a named facet currently smuggled into depth (§5), and the
  flag costs one declaration plus converting one `==` gate to `shows()`.
- `demos/patterns/fidelity.py` (the CLI-harness teaching demo) grows a tag
  declaration so the ladder is visible in the demo that teaches the harness.

## 5. The criterion: depth vs tag

Cheap tags invert the old economics — facets smuggled into `-vv` because
depth was the only free axis can come back out with their names. The gate
that keeps depth from dissolving entirely:

**Depth is anonymous detail; tags are named facets.** Depth answers "how
closely am I looking" — ordered, cumulative, more-of-the-same; the user's
word for it is "verbose." A tag answers "which kind of thing am I looking
at" — a layer with a domain noun the user would actually say: *thinking,
refs, stats, rationale*. The noun test: **would a user ever want X at low
depth without dragging everything else along?** Yes → tag (siftd proved
thinking-at-brief). Only-ever-"more" → depth. `implied_at` restores the
bundle convenience (`-vv` ⇒ everything) without the smuggling.

Seed opportunity list from the survey (validation set for the grammar — each
must be expressible as a pure declaration):

- siftd's `--full` bundle (depth 3 + thinking + tools + no truncation) —
  their unreachable depth=2 shows the real model was always brief/normal +
  named layers.
- loops `fold.py` timestamps (DETAILED/FULL additions a user wants by name
  while debugging telemetry, at any depth).
- `raymarch.py` march stats (§4).
- painted help's `examples` sections; doc-IR's `rationale` (already a tag).

Forward note (not in scope): a declared tag is "a named, toggleable layer of
this view." At rung 2 it materializes as a flag; at the Surface rung the
same declaration can materialize as a runtime toggle (`Fidelity` is frozen
state; toggling is `replace(visible=...)` + re-render). Declare the facet
once; every delivery tier gives it the affordance native to that tier. The
declaration outlives the flag.

## 6. Migration and acceptance

**The acceptance test: siftd's `fidelity_from_args` and loops'
`cli/fidelity.py` become deletable.** Migration must be *moving
declarations* — if it's anything more, the grammar is wrong.

siftd (the forcing-function spec — richest real instance):

```python
SIFTD_TAGS = [
    Tag("thinking", "Show model reasoning", implied_at=3),
    Tag("tools", "Show tool calls and tool output", implied_at=3),
]
# per command: add_cli_args(p, tags=[...subset...], budgets=...)
# at dispatch:  fidelity = parse_fidelity(args, zoom, tags=SIFTD_TAGS)
```

Acknowledged residue, by design:

- siftd's `"text"` baseline tag: always-visible content isn't a layer —
  unconditional rendering needs no tag. Drops out in migration.
- siftd's depth-derived density defaults (`--brief` ⇒ chars=80, `--full` ⇒
  chars=0) stay consumption-side (their `_tool_density` pattern) — the
  grammar carries explicit budgets only.
- siftd's `--tool-chars` (a per-facet budget), siftd's `--tools FILTER`
  optional value (a per-facet filter — the boolean presence is the tag; the
  filter string stays on their namespace), and loops' int-valued `--refs N`:
  app-specific, stay on the `add_args`/`build_fidelity` hooks. Tags are
  boolean layers in this design; valued tags are deferred (§7e).
- siftd's `--brief`/`--full` *spellings* — expressible via `depth_aliases`
  (§4), so they are not residue.

loops: `cli/fidelity.py` deletes in favor of `parse_fidelity(tags=...)`;
the per-view `visible={"facts": "facts"}` mappings become per-lens `Tag`
declarations surfaced by whichever command mounts the lens (declarations
compose up the mounting chain: lens → command → compiler — the same shape
`run_app`/`AppCommand` gives modes). The silent `call_lens` fallback is
loops' to retire, but the whole-spec contract removes its reason to exist.
Both migrations live in their own repos on their own schedule; painted's
gate only validates that the grammar *can* express them (a unit test
encoding siftd's table as declarations and asserting the compiled Fidelity
matches their current parser's output for the same flag combinations).

painted's own migration, same commit series as the grammar:

- `_docs_cli.py`: tags enumerated from the built doc's node tags (the doc
  exists before `run_cli` is called), declared per page — `--rationale`
  exists exactly on pages that have rationale nodes. The generic `--show
  TAG` escape retires with a deprecation note (§7d).
- Demos teaching reform per §4.
- `./dev check` green; `test_public_api.py` updated for the `Depth` removal
  and `Tag` addition; a new unit file pins the compilation laws (implication
  resolution, collision errors, budgets gating, help integration).

## 7. Open questions — RESOLVED 2026-06-10

(a) **Depth-flag aliases** (`--brief` ⇒ 0, `--full` ⇒ 3) — **ACCEPTED**,
    folded into §4 as `depth_aliases: dict[str, int]`. Only siftd needs
    them, but without them siftd keeps a parser and the acceptance test
    fails. One dict, pure spelling, no new concepts.
(b) **Tag negation** (`--no-thinking` to subtract an implied tag from
    `--full`) — **DEFERRED**. No field evidence of demand;
    `argparse.BooleanOptionalAction` is the obvious future path and nothing
    in the compilation rules precludes it.
(c) **`ctx.shows(tag)` sugar** — **DECLINED**. Pure delegation to
    `ctx.fidelity.shows` fails the dissolution test (adds a name, adds
    nothing else). `ctx.zoom` stays the only porthole.
(d) **`--show TAG` generic spelling** — **RETIRED** once the docs CLI
    enumerates its tags into declarations. One spelling per facet; `--show`
    only existed because declarations didn't.
(e) **Valued tags** (loops' `--refs N`) — **DEFERRED, revisit as its own
    design discussion**. `Fidelity.visible` is `frozenset[str]` and stays
    so; re-open on a second consumer needing a per-tag parameter (the seam
    tripwire discipline: re-design on the second instance, not the first).

## 8. Non-goals

- **No `Fidelity` field changes.** The spec survived three independent
  consumers; the gap was never the record.
- **No declarative render idiom imposed.** Rung 1 stays `>=` branching by
  blessing; rung 4 (doc-IR) exists for those who want structure. The field
  had every motivation to invent a selector idiom and chose parsing instead.
- **No `record_line` signature change.** It is a rung-1 citizen; a
  `fidelity=` kwarg can ride a future need.
- **No `paint()` change.** Rung 0's `zoom=` is the rung-appropriate porthole.
- **Downstream adoption is downstream's call.** painted ships the grammar
  and proves expressibility; siftd/loops migrate on their own schedule.
