# tests/ — the gate, tier by tier

`./dev check` is a ten-tier staircase, ordered by cost × blast-radius: the cheapest,
most fundamental failures abort first, so you never read noise from a downstream tier
while the foundation is broken. This doc owns **what each tier is *for*, what shape a
test in it takes, and where a new test belongs.** The gate *ordering* and the one-line
tier summaries live in root `CLAUDE.md` (Level 0) — not repeated here.

Contributor-facing, like `demos/CLAUDE.md` — a standalone file, no README symlink (the
consumer-guide symlink convention is only for `src/painted/{,views,tui}`).

---

## Level 0 — Run one tier

**Trigger**: A tier failed, or I want to run just the tests near my change.

```bash
./dev check              # the whole staircase; must pass before any commit
./dev check -v           # same, but each tier prints verbose (don't swallow output)
./dev test [-v] [args]   # the WHOLE suite in one process (== the cohesion tier), passthrough
./dev test tests/smoke -x -q          # one tier, fail-fast
./dev test tests/unit/test_paint.py   # one file
uv run pytest tests/appearance --update-appearance   # regenerate appearance snapshots
```

Each tier is a plain pytest run over one directory (`tests/smoke/`, `tests/unit/`,
`tests/property/`, `tests/appearance/`, `tests/integration/`), plus three non-pytest
tiers: arch (one unit file, run first and alone), lint (`ty` + `ruff`), outputgen and
docs (`tools.outputgen --check`, `scripts/docs.sh --check`). See `scripts/check.sh` for
the exact invocations.

**Don't reach for yet**: which tier a new test goes in, the snapshot/law mechanisms.

---

## Level 1 — What each tier is FOR, and its test shape

The tier is chosen by **what kind of failure it catches** and **what shape the test
takes** — not by the module under test. A `Block` bug can have a unit test (a specific
regression), a property (an invariant over all inputs), and an appearance snapshot (its
styled output). Same subject, three tiers, because three shapes.

| # | Tier | Dir | Catches | Test shape |
|---|------|-----|---------|-----------|
| 0 | **Arch** | `tests/unit/test_architecture_invariants.py` | layering/import violations, unfrozen state dataclasses, boundary leaks | AST-parses source; **never imports or executes** — pure structure |
| — | **Lint** | (`ty` + `ruff` over `src/`, `tests/typing/`) | type errors, format drift | static analysis; no tests |
| 1 | **Smoke** | `tests/smoke/` | import cycles, broken lazy-facade entries, a demo/tour/slide that raises at all | cheapest thing that can *fail*; imports run, often in a **fresh subprocess** |
| 2 | **Unit** | `tests/unit/` | a specific behavior or regression of one unit | `f(fixed input) → assert exact output` |
| 3 | **Property** | `tests/property/` | an invariant that must hold over *all* inputs | Hypothesis `@given(...)` — a law, not an example |
| 4 | **Appearance** | `tests/appearance/` | the *styled* layer: a role flipping green→red, a header losing bold, a ref appearing/vanishing | `serialize_block(block)` vs a committed JSON snapshot |
| 5 | **Integration** | `tests/integration/` | the assembled `run_cli`/`run_app` path: parse → compile → detect_context → dispatch → stdout | drive the real CLI end-to-end, assert on `capsys` / the renderer |
| 6 | **Cohesion** | (whole `tests/` in one process) | cross-test leaks (sys.modules / lazy-facade / ContextVar) that are green per-tier but red together | re-runs tiers 1–5 in **one** interpreter |
| 7 | **Outputgen** | (`tools.outputgen --check`) | the docs site's committed panels drifting from a fresh render | demo → HTML → markdown, compared to committed |
| 8 | **Docs** | (`scripts/docs.sh --check`) | fragment bodies drifted from source, missing README↔CLAUDE symlinks | docgen currency + symlink presence |

Note the **arch tier only parses** — it can't catch an import-time cycle, so smoke
exists one rung up to actually *import* everything (from a cold cache, so an
order-dependent cycle can't hide behind an already-loaded module). Cohesion is
redundant *by design*: tiers 1–5 run in separate pytest processes, so it re-runs
everything in one process to prove the tiers cohere.

There is no `tests/cohesion/` and no `tests/outputgen/` — those tiers are *modes* of
running the suite you already have, not directories. `tests/typing/` is not a runtime
tier either: it's the curated tree `ty` type-checks (see below), executed by nothing.

---

## Level 2 — Where does a NEW test go?

**Trigger**: I changed something and need to add coverage.

| I changed… | Add a test to… | Because |
|-----------|----------------|---------|
| a pure function's behavior (a bug fix, a new branch) | `tests/unit/test_<module>.py` | a specific input→output regression |
| an invariant that should hold for *any* input (width math, compose arithmetic, writer totality, frozen-state round-trips) | `tests/property/` | Hypothesis proves the law, not one case |
| what a `Block` *looks like* (color, bold, borders, a palette role, a ref/link) | `tests/appearance/` | the char+style+ref grid is the contract object; plain-text asserts can't see Style |
| CLI flag surface, mode dispatch, `run_cli`/`run_app`, exit codes, JSON/live/plain delivery | `tests/integration/` | the assembled path, not a piece of it |
| a TUI Surface/Layer (keys, navigation, modal layers, emissions) | `tests/unit/test_<name>_app.py` via **TestSurface** | app behavior graduated out of demos into unit tests driven by replay |
| a new public export on `painted.core`/`views`/`display`/`publish` | `tests/unit/test_public_api.py` (add to the snapshot) | the semver-major tripwire is bidirectional — a new stable name must be a conscious entry |
| an import/layering rule, or a new frozen state type | `tests/unit/test_architecture_invariants.py` | AST-level structural law |
| a render-model law (destination independence, omission evidence, no downstream policy) | `tests/unit/test_render_model_laws.py` (+ `tests/integration/test_cross_host_content.py` for law 1) | the laws the audit verified by reading are pinned by test |
| a new demo | nothing per-demo — the liveness smoke (`tests/smoke/test_demo_liveness.py`) renders every demo at every zoom; styled/invariant contracts go to the appearance/property tiers | see `demos/CLAUDE.md` |
| a new *published overload* / typed surface | `tests/typing/` (type-checked, never run) | pins guarantees `assert_type` can see but runtime can't |

When two shapes fit, add both — the unit test documents the case you found, the property
guards the class it belongs to. That is the intended relationship, not duplication.

---

## Load-bearing mechanisms

**Ambient-state reset** (`tests/conftest.py`, autouse, suite-wide). painted's identity is
immutability, but palette / icons / borders / vocabularies / ref-schemes are deliberately
process-global ContextVar state. `_reset_ambient_state` pins them all to defaults around
*every* test (and scrubs `NO_COLOR`), so the suite is order-independent and hermetic. A
test that sets an ambient (`use_palette(...)`, `use_refs(...)`) inside its body must scope
it with a `with`, because reset is per-test, not per-Hypothesis-example.

**Appearance snapshots** (`tests/appearance/conftest.py`, the `appearance` fixture). The
successor to the retired demo-text goldens (the golden migration decomposed goldens *by
axis*: character-layer text goldens were deleted; the *styled* axis became these snapshots,
the *invariant* axis became property tests, the *width* axis became width properties). A
snapshot serializes the **cell grid** — each row as coalesced runs of identical style+ref,
each run carrying only its *set* fields — not the writer's lossy ANSI projection. So a
green→red role flip is a one-line JSON diff. Snapshots live under
`snapshots/<module>/<test>/<name>.json`; **the git diff is the review.** A missing snapshot
is *written then failed* on first run — you must see a red→green transition to prove the
assertion binds; auto-passing a bootstrapped snapshot is exactly the hole this closes.
Regenerate deliberately with `--update-appearance`.

**TestSurface** (`src/painted/tui/testing.py`). A non-TTY Surface harness: no alt screen,
no raw mode, no signals. Feed it keys/mouse events, get back `CapturedFrame`s (buffer +
writes) and emissions. This is the *only* way to test a TUI app deterministically — app
tests (`tests/unit/test_*_app.py`) assert on app state and emitted observations, **not**
frame-text snapshots (frame text is brittle; state and emissions are the contract).

**The two semver tripwires.** `test_public_api.py` pins the stable library surface
(`core`/`views`/`display`/`publish`) as a committed `frozenset`, checked *bidirectionally*
against `__all__` — removing a name is a MAJOR break, and adding one silently is caught too
(the diff is the review). `test_architecture_invariants.py` pins layering: framework may
reach the renderer only through lazy imports, state dataclasses must be `frozen=True`, etc.
Both encode the precedent *state the contract → encode it as a law → guard it* — never let
a guarantee live only in prose.

**Property strategies** (`tests/property/strategies.py`, `conftest.py`). The alphabet is
heavily non-ASCII on purpose (wide chars, combining marks) — the teeth are 2-cell
expansion and zero-width dropping, not re-testing wcwidth. The `painted` Hypothesis profile
is `derandomize=True` and `deadline=None` (the same suite runs under coverage, which trips
per-example deadlines); `HYPOTHESIS_PROFILE=thorough` deepens the sweep.

**Drift guards, tiers 7–8.** Outputgen re-renders the docs site's panels from the *same*
library you changed and compares to committed output, so `web/`'s static panels can't
silently drift from the renderer (`./dev panels` regenerates them). Docs checks that
assembled fragment bodies match source (`./dev docs` updates) and that consumer-guide
README↔CLAUDE symlinks are present.

**Cross-tier helpers** (`tests/helpers.py`). `static_ctx()` builds a deterministic
`CliContext`; `block_to_text()` / `row_text()` extract characters; `serialize`-adjacent
comparisons like `assert_blocks_equal()` check cell-for-cell; `capture_content_blocks()`
runs `run_cli` while recording every content `Block` the renderer returned (the law-1
cross-host harness); and the `_iter_imported_modules` / `_assert_no_imports` AST helpers
back both the architecture and render-model law gates.

**Don't reach for yet**: the outputgen manifest internals (`tools/`), the docs fragment
system (`tools/docgen.py`) — those live above tests/.
