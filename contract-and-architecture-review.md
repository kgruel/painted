# painted — Contract & Architecture Review

*Working note, 2026-05-29. Untracked, for later review. Grew out of phase-1 test-suite
work (smoke + Hypothesis property tiers + gated staircase, commit `f98ee22`) — the
property tier surfaced contract drift, which opened the "should the renderer and CLI
framework be split?" question. This captures the full chain of reasoning.*

---

## TL;DR

- **Don't split the renderer and the CLI framework into separate packages.** The seam a
  split would harden (`renderer ↔ cli`) is already your *cleanest, decoupled, heavily-and-
  happily-used* boundary. The seam that is actually bleeding is **`renderer-internals ↔
  power-consumers`**, and a package split does nothing for it.
- **The real problem is implicit contracts.** It shows up in two places with one root
  cause: (a) painted's own lenses drift from their stated width contracts; (b) a downstream
  consumer (fidelis) depends on internals painted never published — and the `core/cli/tui`
  restructure already broke them silently, with no test aware of it.
- **Fix the contract, not the packaging.** Highest-leverage move: a downstream-contract
  test in painted's CI plus a published, layer-tiered public API. Use **stability tiers**
  within one package to resolve the library-vs-framework version tension. Keep the single
  progressive-enhancement import surface — the consumer data shows it's the design *working*.

---

## 1. What stands out (testing perspective)

painted has **world-class structural discipline and a quiet gap between the contracts it
states and the behavior it verifies.**

What's already enforced mechanically (and it's rare and genuinely good):
- Layer boundaries `core ← views ← cli ← tui`, one-directional, checked by AST.
- Every state dataclass proven frozen; mutable-collection fields proven defensively copied.
- Zero-runtime-dep rule held by a test that walks imports.

But all of that proves **structure**. The ~1,400 example tests prove **the happy path
renders correctly**. Almost nothing proved the **contracts** — "width-aware everywhere,"
"a lens honors width," "Surface diff-renders only changed cells," "coverage ≥93%." Those
live in `CLAUDE.md` and docstrings as claims, not as tested guarantees.

The tell: the moment laws replaced examples (the property tier), **two stated contracts
turned out false at the edges on first contact.** The example tests had been confirming the
behavior the author already expected; the properties asked questions the author hadn't.
That gap is where the remaining risk lives.

Specific soft spots observed:
- **Documented targets that nothing enforces.** `cov.sh` has no `--cov-fail-under`; "≥93%"
  is aspirational and the suite is actually at **88%**. An unenforced invariant is worse
  than none — it trains you to half-trust the docs, which corrodes the thing (the AST
  tests) that makes this codebase trustworthy.
- **ContextVar ambient state is the isolation soft spot.** The project's identity is
  immutability, but palette/icons/borders are process-global mutable ContextVars. That's a
  deliberate API choice, but it is the one place test isolation is fragile — it caused
  order-dependent failures twice in a single session. (Mitigated for `tests/property/` with
  an autouse reset fixture; not yet suite-wide.)
- **The most important claim is untested.** "Surface diff-renders: only changed cells
  written" is *the* correctness promise of the TUI subsystem. `TestSurface` exists to verify
  it. It isn't wired. Everything else is polish next to this.

---

## 2. The renderer-vs-CLI split question

### 2.1 Name the tension precisely: library vs framework

A renderer is a **library** — *you call it*: `print_block(border(pad(block)))`. You are in
control; it has no opinion about your lifecycle.

`run_cli` is a **framework** — *it calls you*: you hand it `render(ctx, data)` and `fetch()`
and it drives the loop, detects the TTY, picks the mode. Control is inverted.

These have **opposite stability profiles**: a library should be maximally stable with a
minimal surface; a framework is opinionated and churns as your apps' needs evolve. Bundling
them under one name means the stable thing inherits the churny thing's versioning and
surface. *That* is the splinter — not "two features in a box," but "a library and a
framework with opposite gravity sharing one name."

### 2.2 The decoupling already exists

This is not a tangle to untie. The arch tests already enforce one-directional
`core ← views ← cli ← tui`: `cli/` imports `core` but **not** `views`/`tui`; `views` never
imports `cli`. The old `Zoom`-in-cli violation was resolved (`Zoom` is in `core.zoom`). The
renderer is genuinely clean of the framework, and `Block` (+ `Zoom`) is already a real seam.
The lazy `__init__` facade means `import painted` is cheap and you import only what you touch.

So the question is not "should the boundary exist" — it does, and it's enforced. It's "should
this already-clean seam become a *package* boundary."

### 2.3 The real shape is three deliveries, not two concerns

The `CLAUDE.md` "two concerns" framing undersells the structure. There isn't one framework —
there are **three delivery mechanisms**: `cli` (one-shot), `tui` (interactive), `inplace`
(live). All are the "it calls you" side.

```
substrate (core)  →  meaning (views: lenses/components)  →  delivery (cli | tui | inplace)
        \________________ the library ________________/        \____ the frameworks ____/
```

If you ever split, the honest cut is **library (core+views) vs delivery (cli+tui+inplace)** —
not renderer-vs-CLI. (That also answers "where does the TUI go?")

### 2.4 What the real consumers actually do

Import-surface scan of the consuming repos (AST-classified by entry layer, file counts):

| App | files | renderer (L1) | views | framework (L2) | tui (L4) | live | profile |
|---|---|---|---|---|---|---|---|
| **loops** | 87 | **51** | 5 | 16 | 5 | 2 | renderer-first, some run_cli |
| **siftd** | 190 | 25 | 10 | **175** | – | 5 | almost entirely `run_cli` |
| **fidelis** | 57 | **42** | 21 | 8 | **29** | 1 | renderer + TUI power-user |

(Also: `loops-autoresearch-learn` ≈ loops; `discord-scraper` 1 import. `hlab` imports none.)

Two things fall out immediately:

1. **The CLI-framework boundary you'd split is your cleanest one.** siftd drives `run_cli`
   through a single tidy entry point across 175 files with zero leakage into renderer
   internals. That's a well-behaved framework contract. Not where the pain is.
2. **Entry-layer diversity is real and per-app.** loops = renderer-first, siftd =
   framework-first, fidelis = TUI/renderer. One import surface genuinely serves all three.
   **Progressive enhancement is observed, not aspirational** — and a package split would tax
   exactly the thing that's working (escalating a layer would become a dependency change
   instead of one more `from painted import ...`).

### 2.5 The smoking gun

fidelis routes *past* the public API into internals — and onto module paths the
`core/cli/tui` restructure deleted:

```python
from painted.block import _word_wrap            # now painted.core.block (and private)
from painted._text_width import display_width   # now painted.core._text_width
from painted.buffer import Buffer, CellWrite     # now painted.core.buffer
from painted.fidelity import _setup_defaults     # now folded into painted.cli (and private)
from painted._mouse import parse_sgr_mouse, MouseEvent, MouseButton, MouseAction  # now painted.tui.mouse
```

All five module paths **404 against current painted**. fidelis has no painted pin in its
`pyproject.toml`, so it is either frozen on a pre-restructure painted or already broken — and
**nothing in painted's test suite knows.** The arch tests protect painted's *internal*
consistency; they say nothing about what external consumers depend on.

This is the same disease the property tier found, one level up:
- In-repo: `shape_lens`/`record_line` drift from stated width contracts → contract is
  *implicit*, so it drifted.
- Cross-repo: fidelis depends on internals painted never published as contract, and a
  refactor broke them silently → contract is *implicit*, so it broke.

**Same root cause. A package split fixes neither.** Splitting while the contract is undefined
just yields two under-specified surfaces to break instead of one.

### 2.6 Dissolution test

"Split renderer and CLI into separate packages" — subtract what you already have:

- Decoupling / no cycles → enforced layering already provides it. **Dissolves.**
- "Pick it up at any layer" → lazy facade already provides it; a split would *break* it.
  **Dissolves (and inverts).**
- Independent release → one maintainer, monorepo, versioned together. **Mostly dissolves.**
- **Residue that does not dissolve:** the library-vs-framework **version-coupling tax** —
  the stable renderer riding `cli`/`tui` churn in one version number.

That residue is real, but it's cured by **stability tiers within one package**, not a shard.

### 2.7 Verdict

**Don't split.** The tension you feel is real but *mislocated*. It isn't renderer-vs-CLI —
that seam is clean and heavily, happily used (siftd is proof). It's **"the public API vs the
internals real consumers actually depend on."** A split hardens the seam that isn't bleeding;
publishing and testing the contract fixes the one that is — and it's the natural continuation
of the test work already started.

---

## 3. Findings ledger (candidate bugs / liabilities)

| # | Finding | Status | Decision needed |
|---|---|---|---|
| F1 | `shape_lens` violates its width contract below shape-dependent floors: **string list → 3**, **nested list → 5** (zoom-dependent: z2→3, z3→5, saturates at 5). Integer lists honor width. | Pinned as deterministic guards; broad law restricted to `w≥8`. | Fix the lens, or bless the floors and document them. |
| F2 | `record_line` width is **not zoom-invariant**: FULL grows past `width`; SUMMARY/DETAILED under-fill (content segment is `Block.text(content_str)` with no width arg) and floor-overflow when `width < meta_width+10`. | Universal laws (rectangularity, no-newline, MINIMAL single-row+honors-width) shipped; width law scoped to MINIMAL. | Fix-vs-bless; decide whether non-MINIMAL zooms should pad to width. |
| F3 | Coverage is **88%**, documented target is **≥93%**, and `cov.sh` has no `--cov-fail-under`. Pre-existing gap (unit+golden alone = 87%; property+smoke nudged to 88%) — not a regression. | Unenforced. | Enforce `--cov-fail-under` and close the gap, or lower the documented number to the truth. |
| F4 | **fidelis** imports private symbols on **deleted module paths** (`painted.block`, `painted._text_width`, `painted.buffer`, `painted.fidelity`, `painted._mouse`). Frozen-or-broken against current painted; no pin in its pyproject. | Live liability, untested. | Pin/unbreak fidelis; add a downstream-contract test (see R1). |
| F5 | **Diff-render invariant unverified.** "Surface diff-renders only changed cells" is asserted in docs; `TestSurface` exists but isn't wired to check it. | Untested core claim. | Wire `TestSurface(app, keys) → frames` and assert minimal-write. |
| — | Consumer entry profiles (loops renderer-first, siftd framework-first, fidelis TUI/renderer) — kept for reference; they justify keeping one progressive package. | Reference. | — |

---

## 4. Recommendations (prioritized)

**R1 — Publish the contract and contract-test it against real consumer imports. (Highest leverage.)**
A test in painted's CI that imports exactly the symbols loops/siftd/fidelis actually use.
That single test would have caught the restructure break before it shipped. It is the
cross-repo version of the property tier: *make the contract a tested artifact, not a
convenience.* (Started to offer a draft of this; it's small and lives in the gate.)

**R2 — Promote the load-bearing "internals."** fidelis proves `display_width`,
`Buffer`/`BufferView`, mouse parsing (`parse_sgr_mouse`, `MouseEvent`…), and color conversion
are *public-in-practice*. Their `_`-privacy is a gap in painted's API completeness, not only
fidelis misbehaving. Give them an explicit home (`painted.tui` exposes some; formalize the
rest, e.g. `painted.lowlevel` or `__all__`).

**R3 — Stability tiers, not a split.** Declare `core`+`views` the semver-stable public API;
`cli`+`tui` evolving. Document it. One install, differential guarantees. This resolves the
library-vs-framework version tension without a dependency graph or two changelogs.

**R4 — Wire the diff-render test.** `TestSurface` → frames → assert only changed cells were
written. The single most important unverified claim in the codebase.

**R5 — Enforce or delete the 93% target.** Add `--cov-fail-under` and either close the gap or
set the number to the truth (88%). Match the energy of the AST tests.

**R6 — Suite-wide ambient-state reset.** One root-conftest autouse fixture resetting
palette/icons/borders, so isolation is a property of the suite, not a thing each test dir
remembers. (Only `tests/property/` is covered today.)

**R7 — Decide fix-vs-bless on F1/F2.** Sets the policy for everything the broader property
tier will surface later: does a failing law mean "fix the code" or "the contract allows that"?

**R8 — Unbreak/pin fidelis** (and let R1 keep it honest going forward).

**What NOT to rush:** the deferred writer/color/html property files. More laws without
settling F1/F2 just finds more drift you haven't decided to fix — it raises anxiety without
resolving it. Establish the contract stance first; breadth of laws pays off *after* a failing
law reliably means "fix the code."

---

## 5. Context: what shipped this session (commit `f98ee22`)

Phase 1 of the test-suite arc:
- Gate restructured into a fail-fast staircase: `Arch → Lint → Smoke → Unit → Property →
  Golden → Outputgen` (Unit no longer double-runs the arch file).
- **Smoke tier** (`tests/smoke/`): subprocess-based import/cycle/lazy-facade checks (the
  cheapest test that can fail; subprocesses so it can't pollute the shared interpreter).
- **Property tier** (`tests/property/`): 7 files + shared strategies; `derandomize=True` for
  gate reproducibility (`thorough` profile stays exploratory). Mutation-confirmed teeth.
- 1,435 tests green and deterministic.

Phase-2 backlog (also in session memory `test-suite-arc.md`): writer/color/html property
files, TestSurface wiring (R4), run_cli-e2e → integration tier split, goldens audit, and the
fix-vs-bless decisions above. Note: `derandomize=True` means the gate no longer explores new
inputs — exploration is now manual via `HYPOTHESIS_PROFILE=thorough`.

---

## Appendix — methodology / caveats

- Consumer numbers are from AST-parsing `import painted*` statements across
  `~/Code/{loops,siftd,fidelis,hlab}`, classified by layer; **import-surface analysis, not
  full semantic usage**. The layering signal is unambiguous; exact occurrence counts are
  indicative.
- "Deleted module paths" verified by `import painted.block` etc. raising `ModuleNotFoundError`
  against current painted.
- Coverage figures from `./dev cov` (branch coverage, `src/painted`).
