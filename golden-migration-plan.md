# Golden-test migration plan — decompose by axis

**Source:** triage workflow `wf_6f77692b-8b6` (26 agents: 24 golden-triage + 1 inventory + synthesis), 2026-05-31.

## Decision (ratified)

Demo-coupled "golden" tests snapshot **color-stripped plain text** (`block_to_text` defaults `use_ansi=False`), conflating three jobs on one brittle artifact. Decompose **by test axis**. Demos stop being test fixtures — they survive only as (1) a **liveness smoke** ("they still run") and (2) **doc source** for outputgen.

Rationale: couple things that change for the *same* reason. Invariants change ~never, demos change for *pedagogy*, contracts change for *correctness* — three clocks, three homes. The bundle forced all three to the slowest, noisiest clock.

## Axis routing

### Liveness (floor — build FIRST)
One `tests/smoke/test_demo_liveness.py`, parametrized per artifact, covering **28 demos + tour + 21 slides**. Tier-dispatched render-without-raising:
- **primitives** (cell/compose/show/span_line) — call `demo()` under `redirect_stdout`, assert non-empty
- **patterns** (12) — `_fetch()` + `_render(static_ctx(zoom), data)` per zoom (special-case `rendering.py` flag-dispatch; `palette_icons._render_minimal(ctx)` takes only ctx)
- **apps** (8) + **examples** (4) — `TestSurface(App(), input_queue=[...,'q']).run_to_completion()`
- **tour** — insert `demos/` on `sys.path`, `build_slides()` + `run_quiet_mode(...)` under stdout capture (renders every slide × zoom, no TTY)
- **slides** — `load_slides_dir` + `validate_slides` (parse-level; render-level subsumed by tour)

### Property (mostly already covered — the dissolution confirmed)
| Law | Status | Source goldens |
|---|---|---|
| width-exact + reflow | **already-covered** | 16 goldens |
| rectangular + no-orphan-wide | **already-covered** | 7 |
| compose arithmetic (border/join/pad/truncate/wrap) | **already-covered** | 6 |
| id-propagation through compose | **already-covered** | hit_testing |
| lens width-exactness (chart/tree/flame/shape) | **already-covered** | 5 |
| **Surface frame is W×H, fully filled, rectangular** | **NEW** → `tests/property/test_surface_invariants.py` | 8 app replays |
| bar-fill proportionality (filled+empty==bar_w) | **extend-existing** | animation/fidelity/profiler/timing |
| viewport scroll-containment | already-covered | viewport/widgets |
| focus-ring closure (permutation cycle) | already-covered | focus_form/widgets |
| ASCII purity (≤127 under ASCII_ICONS) | **extend-existing** | palette_icons/show |
| Style.merge precedence | **extend-existing** → unit | cell |
| ambient propagation (current_icons/palette) | already-covered | palette_icons |

### Appearance (NEW — suite-owned, style-capturing; build AFTER representation decision)
4–5 canonical scenarios, **not** demo-coupled:
1. **style-catalog** — every fg/bg × {bold,italic,underline,dim,reverse} + a `Style.merge` row (← cell, span_line)
2. **palette-role legend × DEFAULT/NORD/MONO** — 5-role chip block; the three renders MUST differ (← 8 goldens; this is the "same render, different ambient palette" lesson that strips to byte-identical text)
3. **threshold-colored dashboard row** — usage/timing past 75/90/hot thresholds; green/yellow/red fg, `p.accent` hot phase (**currently wholly unguarded — highest-value new artifact**) (← fidelity/timing/layers/responsive/live)
4. **focus/selection frame** — focused component + selected row + cursor + status bar, per focus mode (← 8 goldens; reverse-video selection, cursor `Style(reverse=True)`, focused-vs-dim border roles)
5. **component-state styling** — spinner + progress at fixed state (cyan+bold spinner, green+bold fill vs dim empty); *may fold into #4*

### Behavior (graduate to `tests/unit/`, TestSurface-driven, assert state/emissions — NOT stripped frame text)
10 ports: animation, focus_form, layers_app, minimal, mouse, search_filter, widgets, focus, testing(DeployApp), live(spinner/stream). (viewport/layers-pattern/show/help/hit_testing already owned elsewhere.)

### Liveness-only (snapshot fully retired once liveness + appearance land)
help, layers, compose, rendering, hit_testing, palette_icons, fidelity, timing, profiler, show, span_line, cell.

## Execution order (safety rule: never delete coverage before its replacement exists)
1. **Liveness smoke** (all 28 + tour + slides). Nothing deleted.
2. **Extend property tier** — new Surface-frame law; bar-fill proportionality; ASCII-purity + Style.merge to unit homes. Don't touch goldens.
3. **Appearance scenarios** — only after representation decided.
4. **Graduate 10 behavior replays** to unit.
5. **Delete demo-coupled snapshots one at a time**, each only after its specific replacement landed.
6. Wire appearance scenarios into outputgen as doc source; prune dead `goldens/*.txt`.

## Open decisions
1. **APPEARANCE REPRESENTATION — RESOLVED 2026-05-31: (b) structured char+style map.** Appearance goldens serialize the cell grid to JSON per-cell `{char,fg,bg,attrs}` — diff-stable, normalizer-safe, faithful to the cell-buffer contract (painted's universal type *is* the styled grid; raw ANSI is a lossy projection through the writer). The writer's ANSI-byte correctness is a **separate** concern: covered by the property tier (SGR down-conversion totality) + a few targeted `sgr(Style(...)) == "\x1b[..."` assertions. A new appearance fixture (not the rstripping golden `assert_match`) serializes a Block/frame to the structured form and diffs it.
   - rejected: (a) raw ANSI — corrupted by the rstrip normalizer, brittle on SGR ordering/coalescing; (c) targeted-only — keep as a *supplement* for writer bytes, not the primary artifact (loses the holistic frame).
2. Fold component-state styling into focus/selection frame? (scenario count 4 vs 5)
3. Promote already-covered unit laws (viewport/focus-ring/id-prop) to Hypothesis properties? (non-blocking)
4. `disk.py` liveness — scans real FS on construction; include as-is / inject fixture root / exclude?
5. Threshold appearance data — suite-owned fixtures vs derived from demo `SAMPLE_*` (latter re-couples)?

## Risks
- Raw-ANSI corruption by the rstrip normalizer (decision 1 — resolve before any appearance snapshot).
- Deleting a behavior-primary golden before its replacement drops the ONLY key→state→frame coverage. Honor step-5 per-golden gate.
- tour/slides need `demos/` on `sys.path` before `import slide_loader` — else liveness silently skips them.
- `disk.py` live-FS nondeterminism in CI.
- Behavior graduations assert on app internals (`progress_state.value`, `focus.id`, `picked`…) — confirm each is public/stable, else assert via emissions/frames.
- "already-covered" statuses verified by **test-name grep, not assertion bodies** — spot-check fidelity/live/timing/profiler/rendering before retiring their goldens.
- Liveness "no raise" is weak — ensure appearance/behavior replacements exercise the *same* render path, not a reduced one.
