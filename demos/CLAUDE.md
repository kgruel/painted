# demos/ — CLAUDE.md

## What We're Doing

Walking back through what we've built to create a progressive set of
educational demos. Many existing demos were stepping stones during API
development — they reference deleted helpers, reach up the stack, or
demonstrate intermediate APIs that no longer exist. We're replacing them
with demos that teach the final API cleanly.

Drop demos that no longer make sense. Don't preserve something just
because it exists.

## Demo Rules

1. **PEP 723** — `# /// script` metadata, runnable via `uv run demos/primitives/foo.py`
2. **Visual, not explanatory** — no `print()` commentary. The output is the lesson. Use styled Block headers (dim) for section labels.
3. **Own layer only** — use exactly the API you're demonstrating. Don't reach up the stack. Output primitives (`print_block`, `join_vertical`, `Block.text()` for headers) are the baseline display mechanism.
4. **`to_X` bridges are fair game** — each demo can use its type's bridge to the next layer (e.g. `Line.to_block()`). The ladder shows the manual version of what the next step automates.
5. **Sections as `join_vertical` groups** — dim header, spacer, content. Consistent visual rhythm.
6. **Real-ish sample text** — terminal output, deploy messages, status lines. Not "Hello world".
7. **Maker's notes go through the plaque** (`demos/showcase/_plaque.py`) — `Plaque` + `render_plaque` + the shared `NOTE_TAG`. A note is named-only (`--note`, implied at no depth), capped, and signed; those three conventions are held by `tests/unit/test_plaque.py`, not by review. Demos may import private siblings: every loader puts a demo's own directory on `sys.path`.

## Demo Tiers

Four test-shape tiers (distinguished by where state lives and how you test them),
plus **Showcase** — a *presentation* tier, not a new test shape.

| Tier | Lesson | State | Test shape |
|------|--------|-------|------------|
| **Primitive** | Type API | None | `function() → stdout capture` |
| **Pattern** | Workflow | Data only | `_render(data, fidelity, width) → Block` |
| **App** | Interaction | Mutable (Surface) | `TestSurface(keys) → frames` |
| **Example** | Real app | Mutable (Surface) | `TestSurface(keys) → frames` |
| **Showcase** | Spectacle | Data only | `_render(data, fidelity, width) → Block` *(pattern shape)* |

**Primitives** teach a single type or composition. No `main()`, no CLI flags.
Output via `print_block` / `paint`. The output is the lesson.

**Patterns** are runnable examples with CLI flags — the invocation IS the lesson.
They expose `_fetch()` and `_render(data, fidelity, width) → Block` (the renderer
contract, docs/RENDERER_CONTRACT_DESIGN.md — declared via `renderer=`), exercised
by the liveness
smoke (`tests/smoke/test_demo_liveness.py`) — every pattern renders at every zoom
without raising. Styled/invariant contracts live in the appearance/property tiers,
not in per-demo snapshots.
A pattern may offer `-i` interactive mode **only** when it's a live frame around
the same `_render` function (e.g. responsive.py). If `-i` introduces new state
or its own render pipeline, it's an app.

**Apps** have their own state machines: selection, navigation, modal layers.
`surface.render()` owns the layout. Tested via `TestSurface` replay: send keys,
assert on captured frames and emissions.

**Examples** are miniature applications that show what you can build, not teach
individual concepts. They use the full API freely — the experience is the lesson,
the code is reference material. Same test shape as apps (TestSurface).

**Showcase** demos share the pattern test shape exactly (`_fetch()` + `_render`
at every zoom, surface-delivered animation) — they are *not* a new boundary. They
live in their own `showcase/` directory because pedagogically they're spectacle,
not teaching: full-screen, animated, "look what painted can do." The defining
property is entry through `showcase_main` (`demos/showcase/_harness.py`), which
fixes surface delivery for the tier. `painted demos`
renders them as a distinct fifth column (the finale); the liveness smoke exercises
them via `test_showcase_demo_renders`, identical assertions to patterns.

Because showcases are spectacle rather than teaching, their **entry point is
scaffolding and is shared** — `showcase_main` + `ShowcaseArg` + `plate`, with
`_plaque` for the maker's note. A demo declares each argument once and the
harness spends it on both the parser and `--help`. This stops at the showcase
boundary on purpose: a pattern's `run_cli` call *is* its lesson (rule 3, and
"the invocation IS the lesson" above), so harnessing it there would delete the
curriculum. Conventions are held by `tests/unit/test_showcase_harness.py` — a
shrink-only allowlist for unmigrated files, and the rule that a `stats` facet
is implied at `-vv`.

The test shape *is* the boundary between primitive / pattern / app. If you can
test the full lesson by calling `_render(data, fidelity, width)`, it's a pattern
(or, if it's animated spectacle, a showcase). If you need to send keys and
inspect frames, it's an app.

## Demo Ladder

Each demo uses the API at its level. The code *is* the lesson.

```
primitives/
  cell.py           Style + print_block                        ✓
  span_line.py      Span, Line, to_block()                     ✓
  compose.py        join, border, pad, truncate, Wrap, Align   ✓
  diagnostics.py    render_traceback: stdlib-vs-painted delta, zoom ladder, redacted locals, ExceptionGroup tree ✓
  errors.py         Exception hierarchy: introspected class tree, each contract broken + logged ✓
  logging_handler.py PaintedHandler: declared severities, extra= payload, exc_info composition ✓
  refs.py           Refs: RefScheme + use_refs, denotation → OSC 8 link, inert cases ✓
  paint.py          paint() transcription: scalars, dict, list, nested, declared schemas ✓

patterns/
  rendering.py      Rendering patterns: --explicit, --custom, --palette   ✓
  denotation.py     Refs in a lens: refed record lines, resolve_ref table, hit probes ✓
  palette_icons.py  Ambient config: Palette + IconSet switching           ✓
  hit_testing.py    Hit testing: Block.ref -> composition -> Buffer.hit()  ✓
  fidelity.py       CLI harness: -q → default → -v → -vv      ✓
  responsive.py     Responsive layout: join_responsive + breakpoints (-i) ✓
  table.py          Table construction: fixed→AUTO→Fill→responsive ladder, column-drop priority, live -i reflow ✓
  live.py           Live streaming: fetch_stream, spinners, --live        ✓
  focus.py          Focus + Cursor + Search: navigation vs capture        ✓
  testing.py        Replay testing: emit capture, observation traces      ✓
  profiler.py       Self-profiling: frame cost, emission timeline, flame  ✓
  help.py           Zoom-aware help: HelpData rendered at each zoom level ✓
  prompts.py        Declared prompts: real default record lines + refusal text, non-interactive ✓

apps/
  (behavior graduated to tests/unit/test_*_app.py — TestSurface drives keys,
   tests assert app state + emissions, not frame-text snapshots)

examples/
  disk.py           Real filesystem disk usage visualization    ✓
  big_text.py       Block character rendering (multiple sizes)
  lenses.py         Tree and chart data visualization
  theme_carnival.py Interactive palette explorer

showcase/           (pattern test shape; surface-delivered animated spectacle)
  life.py           Conway's Life: pure step + fetch_stream animation     ✓
  donut.py          donut.c: scene as pure function of a frame counter    ✓
  plasma.py         Plasma field: per-cell color as data, truecolor ramp  ✓
  fire.py           Doom fire: seeded LCG — randomness as frozen data     ✓
  boids.py          Boids: continuous agents projected onto cells         ✓
  lorenz.py         Lorenz: trails as frozen data, chaos law-tested       ✓
  wireworld.py      Wireworld: ASCII-art circuits, laws verify computing  ✓
  raymarch.py       SDF raymarcher: scene as expression tree, donut re-derived ✓
  starmap.py        The night sky: real catalog, refs make every star a link ✓
  mandelbrot.py     Escape time: proof vs presumption, the unknown declared ✓
  harmonograph.py   Damped pendulums: Braille subpixels + capability carriers ✓
```

Old stepping stones (`block.py`, `buffer.py`, `buffer_view.py`) deleted —
their content is covered by the ladder or belongs at a different level.
Redundant fidelity demos (`fidelity.py`, `fidelity_health.py`) and
dissolved `show.py` deleted — one canonical example per concept.
