# Live Delivery — the two-tier contract and the alt-screen LIVE path

**Status: RATIFIED 2026-06-09, not yet implemented.** This document is the
handoff brief for the implementation session. The contract below is decided;
the open questions in §5 are the implementer's to settle (with the user).

## 1. The contract

Two delivery tiers for live output, discriminated by *where the output lives*:

| Tier | Mechanism | Lives in | For |
|------|-----------|----------|-----|
| **Ephemeral liveness** | `InPlaceRenderer` (normal screen, relative cursor) | the scrollback | spinners, progress bars, short-lived status — anything where the final state belonging to terminal history is the point, and nobody scrolls mid-run |
| **Sustained animation** | Surface machinery (alt screen, absolute addressing, per-cell diff) | its own screen | long-running animated views — anything a user might watch, background, scroll past, or split around |

`run_cli`'s LIVE mode currently always uses InPlaceRenderer. The change: give
LIVE an alt-screen delivery path for sustained streams, with a **final-frame
deposit** — on finish or `q`, the last frame is printed to the normal screen
as static output. Smoothness of the alt screen, scrollback persistence of
in-place. Both halves are already proven in the codebase (see §3).

## 2. Why (the evidence trail, compressed)

Four field rounds against flickering `--live` demos (ghostty, macOS), each
fix measured and insufficient until the mechanism was found:

1. **Blank-phase clear+redraw** — InPlace erased the whole region before
   redrawing; line-buffered stdout flushed per newline (h+ partial writes per
   frame). Fixed (`49ae3da`): overwrite-in-place, one atomic write, DEC 2026
   sync wrap. Flicker reduced, not gone.
2. **Full-frame rewrites** — every row rewritten every frame. Fixed
   (`0b515f7`): row-diffing, unchanged rows become cursor hops. Life frames
   dropped ~45% in bytes. Flicker *still* largely unchanged.
3. **Renderer differential** (`ae3f3e1`): the same `_render` delivered via
   Surface (`life.py -i` / `donut.py -i`) is glass-smooth, foreground and
   background. Delivery indicted.
4. **Mechanism isolated (field repro)**: `--live` + *scrolling during the
   run* reproduces tearing/banding on demand; window arrangement is
   irrelevant. Normal-screen relative addressing ("cursor up N from where I
   was") breaks when the viewport moves: writes land on wrong visual rows
   and disturbed regions repaint. Stacked ghost frames in scrollback are the
   same failure (cursor-up can't reach over scrolled content; the renderer
   reprints). The alt screen is **structurally immune** — no scrollback, no
   relative anchor.

Conclusions that bound the design: write *content* was never the lever
(rounds 1–2); per-cell granularity in InPlace would not fix the repro (the
coordinate system is the defect, not the byte count); the DEC 2026 wrap is
kept (free, correct) but is not load-bearing for this problem.

## 3. What already exists

- `demos/patterns/life.py` / `donut.py` `_run_interactive()` — hand-rolled
  versions of exactly this delivery: a `Surface` subclass whose `update()`
  advances pure state, `render()` paints `_render(ctx, state)` at (0,0),
  `q` quits / space pauses. The generic path replaces these hand-rolled
  handlers; they are the acceptance fixture.
- `CliRunner._run_live` (`src/painted/cli/runner.py`) — the current LIVE
  dispatch: streams `fetch_stream` through InPlaceRenderer (TTY) or prints
  the final frame (non-TTY). The non-TTY branch is untouched by this design.
- `tui/Surface` — alt screen, keyboard, per-cell diff render, `fps_cap`.
- `finalize()` semantics on InPlaceRenderer — the deposit concept already
  exists there; the alt-screen path generalizes it ("leave the last frame
  behind on the normal screen").

## 4. The design

A generic stream-consuming Surface (working name `StreamSurface`), private to
the cli package:

- Hosts the app's `fetch_stream()` as an asyncio task alongside `Surface.run()`.
  Each yielded state is stored and `mark_dirty()` is called; `render()` paints
  `render(ctx, state)` at (0,0). The *stream* paces state (it already sleeps);
  `fps_cap` only bounds repaint.
- Keys: `q`/ctrl-c stop; `space` pause is nearly free (stop consuming the
  iterator) — include it.
- On exit (stream exhausted or quit): leave the alt screen, then
  `print_block(render(ctx, last_state))` to the normal screen — the deposit.
  Exhausted-stream behavior should match today's `--live` end state.
- `CliRunner._run_live` chooses delivery per §5(a); everything else
  (`detect_context`, JSON short-circuit, plain pipes) is unchanged.

**The single-renderer substrate (deferred, separate refactor):** Surface's
buffer diff and InPlace's row diff are two implementations of one damage
engine. Unifying them (damage computation in core; deliveries translate
damage to absolute-alt-screen vs relative-scrollback writes) is real but is
NOT required for this change and should not ride along.

## 5. Open questions for the implementer

(a) **How does LIVE choose its delivery?** The discriminator is exclusivity:
    in-place liveness composes with other stdout (logs above a status line);
    alt screen takes the terminal over. Duration can't be known a priori.
    Recommendation: an explicit knob on `run_cli` (e.g.
    `live_delivery="inplace" | "surface"`, default `"inplace"` for
    back-compat), demos opt in. A `--live=surface` CLI spelling or similar
    is possible but probably over-exposed. Settle with the user.
(b) **Deposit fidelity** — deposit the last frame at the *current* zoom and
    width? (Recommendation: yes, exactly what was on screen.)
(c) **live.py (health checks)** — short stream; works fine on either path.
    Leave it on inplace unless the user wants otherwise; it is the canonical
    "ephemeral" citizen.
(d) **Does Surface want the DEC 2026 wrap too?** Cheap to add at its flush
    point; orthogonal, do it if trivial.

## 6. Acceptance

- `life.py --live` / `donut.py --live` (opted into surface delivery): smooth
  under backgrounding AND under the scroll repro (structurally — alt screen
  cannot be scrolled into); final frame present in scrollback after exit.
- The demos' hand-rolled `-i` handlers replaced by (or reimplemented over)
  the generic path — `-i` and `--live` may well converge to the same
  delivery, differing only in default interactivity affordances.
- `tests/smoke/test_demo_liveness.py` untouched and green (it exercises
  `_fetch`/`_render`, not delivery).
- Existing InPlaceRenderer laws (`tests/unit/test_inplace_renderer.py`)
  untouched and green — InPlace itself does not change.
- Full `./dev check` green.
