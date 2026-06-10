#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Conway's Life — a pure pattern, animated by the harness.

The world is frozen data, the step is a pure function, the render is a pure
function — time comes from the CLI harness, not the demo. `fetch_stream`
yields successive generations and InPlaceRenderer repaints only the cells
that changed; the same render function serves the static snapshot, the live
animation, and the plain-text pipe. Two grid rows share one terminal row via
half-block glyphs (▀ ▄ █), so the picture stays square-ish without color
tricks — it survives `| cat` untouched.

    uv run demos/patterns/life.py                    # snapshot at generation 100
    uv run demos/patterns/life.py --live             # animate from the seed
    uv run demos/patterns/life.py --seed acorn -v    # grid + population sparkline
    uv run demos/patterns/life.py --gen 300 -vv      # bordered, full stats
    uv run demos/patterns/life.py -q                 # one-line census
    uv run demos/patterns/life.py --json             # the grid as data
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from time import perf_counter

from painted import (
    Block,
    CliContext,
    OutputMode,
    Style,
    Zoom,
    border,
    join_horizontal,
    join_vertical,
    run_cli,
    truncate,
    ROUNDED,
)
from painted.cli import HelpArg
from painted.palette import current_palette
from painted.views import sparkline


# --- Data: a frozen world ---

_COLS, _ROWS = 64, 44  # logical grid; renders 64 wide x 22 tall via half-blocks
_HISTORY_CAP = 120  # population samples kept for the sparkline

Cells = tuple[tuple[int, int], ...]  # sorted live coordinates — JSON-friendly


@dataclass(frozen=True)
class LifeWorld:
    cells: Cells
    cols: int
    rows: int
    generation: int
    seed: str
    history: tuple[int, ...]  # population per generation, capped
    # Observed render+write cost per frame, ms — measured by the stream at its
    # yield boundary, empty for static snapshots. Timings are *inputs* to the
    # render, so render stays a pure function and static output stays undressed.
    frame_ms: tuple[float, ...] = ()


# Classic seeds, in their conventional coordinates (centered at world-build).
SEEDS: dict[str, Cells] = {
    "r-pentomino": ((1, 0), (2, 0), (0, 1), (1, 1), (1, 2)),
    "glider": ((1, 0), (2, 1), (0, 2), (1, 2), (2, 2)),
    "acorn": ((1, 0), (3, 1), (0, 2), (1, 2), (4, 2), (5, 2), (6, 2)),
}

DEFAULT_SEED = "r-pentomino"
DEFAULT_GEN = 100  # static snapshot: deep enough into the run to look alive


def seed_world(seed: str = DEFAULT_SEED) -> LifeWorld:
    """Build generation 0: the named seed centered on the torus."""
    pattern = SEEDS[seed]
    w = max(x for x, _ in pattern) + 1
    h = max(y for _, y in pattern) + 1
    ox, oy = (_COLS - w) // 2, (_ROWS - h) // 2
    cells = tuple(sorted((x + ox, y + oy) for x, y in pattern))
    return LifeWorld(
        cells=cells,
        cols=_COLS,
        rows=_ROWS,
        generation=0,
        seed=seed,
        history=(len(cells),),
    )


# --- The step: pure function, torus topology ---


def step(world: LifeWorld) -> LifeWorld:
    """One generation: B3/S23 on a wrapping grid. Same world in, same world out."""
    live = set(world.cells)
    counts: dict[tuple[int, int], int] = {}
    for x, y in live:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    key = ((x + dx) % world.cols, (y + dy) % world.rows)
                    counts[key] = counts.get(key, 0) + 1
    cells = tuple(sorted(c for c, n in counts.items() if n == 3 or (n == 2 and c in live)))
    return replace(
        world,
        cells=cells,
        generation=world.generation + 1,
        history=(*world.history, len(cells))[-_HISTORY_CAP:],
    )


def _advance(world: LifeWorld, generations: int) -> LifeWorld:
    for _ in range(generations):
        world = step(world)
    return world


# --- Fetch: snapshot and stream ---


def _fetch(seed: str = DEFAULT_SEED, generation: int = DEFAULT_GEN) -> LifeWorld:
    """Static snapshot: the seed advanced to a fixed, deterministic generation."""
    return _advance(seed_world(seed), generation)


_FPS = 15
_MAX_GENS = 450  # ~30s of animation before the demo bows out on its own
_METER_CAP = 60  # frame-cost samples kept for the meter


async def _fetch_stream(seed: str = DEFAULT_SEED) -> AsyncIterator[LifeWorld]:
    """Animate from the seed; stop on death, stasis, or short oscillation.

    The time from each `yield` to its resume is the harness consuming the
    frame — render plus write — so the stream is the one place frame cost
    can be observed without touching the runner. Each measurement rides
    into the *next* world's frame_ms: a trailing gauge.
    """
    budget = 1.0 / _FPS
    world = seed_world(seed)
    t0 = perf_counter()
    yield world
    cost = perf_counter() - t0
    prev: Cells = ()
    prev2: Cells = ()
    while world.generation < _MAX_GENS:
        await asyncio.sleep(max(0.0, budget - cost))
        prev, prev2 = world.cells, prev
        world = step(world)
        world = replace(world, frame_ms=(*world.frame_ms, cost * 1000)[-_METER_CAP:])
        t0 = perf_counter()
        yield world
        cost = perf_counter() - t0
        if not world.cells or world.cells == prev or world.cells == prev2:
            break  # extinct, still life, or period-2 — the show is over


# --- Render helpers ---

_GLYPHS = (" ", "▀", "▄", "█")  # indexed by upper-occupied | lower-occupied << 1


def _grid(world: LifeWorld, width: int) -> Block:
    """The world as half-block rows: two grid rows per terminal row."""
    live = set(world.cells)
    style = current_palette().accent
    rows: list[Block] = []
    for ty in range(world.rows // 2):
        chars = []
        for x in range(world.cols):
            idx = ((x, 2 * ty) in live) | (((x, 2 * ty + 1) in live) << 1)
            chars.append(_GLYPHS[idx])
        rows.append(Block.text("".join(chars), style))
    return truncate(join_vertical(*rows), width)


def _census(world: LifeWorld) -> Block:
    # Counters are width-padded so changing digit counts never shift the row.
    p = current_palette()
    return join_horizontal(
        Block.text(world.seed, p.accent.merge(Style(bold=True))),
        Block.text(f"  gen {world.generation:>3}  pop {len(world.cells):>3}", Style(dim=True)),
    )


def _pop_sparkline(world: LifeWorld, width: int) -> Block:
    # Fixed width from frame 0 — sparkline pads until history fills it, so
    # the window never widens as samples accumulate.
    spark_w = max(8, width - 12)
    return join_horizontal(
        Block.text("pop ", Style(dim=True)),
        sparkline(list(world.history), spark_w, style=current_palette().success),
        Block.text(f" {len(world.cells):>3}", Style(dim=True)),
    )


def _meter(frame_ms: tuple[float, ...], fps: int, width: int) -> Block | None:
    """The in-frame gauge: observed frame cost against the fps budget.

    Returns None when there are no observations (static output) — the live
    dress follows the data, not a flag.
    """
    if not frame_ms:
        return None
    p = current_palette()
    cost, budget = frame_ms[-1], 1000.0 / fps
    role = p.success if cost < budget * 0.5 else p.warning if cost < budget * 0.9 else p.error
    spark_w = max(8, width - 27)  # 27 = the row's fixed label chars; spark + labels == width
    return join_horizontal(
        Block.text("cost ", Style(dim=True)),
        sparkline(list(frame_ms), spark_w, style=role),
        Block.text(f" {cost:5.1f}ms ", role),
        Block.text(f"/ {budget:.0f}ms budget", Style(dim=True)),
    )


def _window(world: LifeWorld, width: int, *extra: Block) -> Block:
    """The dressed viewing frame: grid, census, live meter, and any extras.

    Inner width pins to the grid — every row is sized against it, so the
    border never moves no matter what the data rows do.
    """
    w = min(width - 4, world.cols)
    rows = [_grid(world, w), truncate(_census(world), w)]
    meter = _meter(world.frame_ms, _FPS, w)
    if meter is not None:
        rows.append(truncate(meter, w))
    rows += [truncate(b, w) for b in extra]
    return border(join_vertical(*rows), title="Conway's Life", chars=ROUNDED)


# --- Zoom renderers ---


def _render_minimal(world: LifeWorld, width: int) -> Block:
    return truncate(_census(world), width)


def _render_summary(world: LifeWorld, width: int) -> Block:
    return _window(world, width)


def _render_detailed(world: LifeWorld, width: int) -> Block:
    w = min(width - 4, world.cols)
    return _window(world, width, _pop_sparkline(world, w))


def _render_full(world: LifeWorld, width: int) -> Block:
    w = min(width - 4, world.cols)
    peak = max(world.history)
    density = len(world.cells) / (world.cols * world.rows)
    stats = Block.text(
        f"seed {world.seed}  ·  gen {world.generation:>3}  ·  "
        f"pop {len(world.cells):>3}  ·  peak {peak:>3}  ·  density {density:.1%}",
        Style(dim=True),
    )
    return _window(world, width, _pop_sparkline(world, w), stats)


def _render(ctx: CliContext, world: LifeWorld) -> Block:
    if ctx.zoom == Zoom.MINIMAL:
        return _render_minimal(world, ctx.width)
    if ctx.zoom == Zoom.DETAILED:
        return _render_detailed(world, ctx.width)
    if ctx.zoom == Zoom.FULL:
        return _render_full(world, ctx.width)
    return _render_summary(world, ctx.width)


# --- Interactive: the same _render, delivered by Surface ---


def _run_interactive(ctx: CliContext, seed: str) -> int:
    """-i: a live frame around the same _render, on the alt screen.

    The renderer differential: --live delivers frames through
    InPlaceRenderer (relative cursor walk, normal screen buffer); -i
    delivers the same frames through Surface (per-cell diff, absolute
    positioning, alt screen). Comparing the two under identical content
    isolates the delivery mechanism. No meter row here — frame_ms is a
    stream affordance; Surface owns its own loop.

    Keys: space pauses, q quits.
    """
    from painted.tui import Surface

    class LifeSurface(Surface):
        def __init__(self) -> None:
            super().__init__(fps_cap=_FPS)
            self.world = seed_world(seed)
            self.paused = False

        def update(self) -> None:
            if self.paused:
                return
            self.world = step(self.world)
            self.mark_dirty()

        def render(self) -> None:
            self._buf.fill(0, 0, self._buf.width, self._buf.height, " ", Style())
            _render(ctx, self.world).paint(self._buf, 0, 0)

        def on_key(self, key: str) -> None:
            if key == "q":
                self.quit()
            elif key == "space":
                self.paused = not self.paused

    asyncio.run(LifeSurface().run())
    return 0


# --- Entry point ---


def main() -> int:
    # Demo-specific args are peeled off before run_cli; help_args puts them
    # back in --help. The closures below freeze the choice into fetch/stream.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--seed", choices=sorted(SEEDS), default=DEFAULT_SEED)
    pre.add_argument("--gen", type=int, default=DEFAULT_GEN)
    ns, rest = pre.parse_known_args(sys.argv[1:])

    return run_cli(
        rest,
        render=_render,
        fetch=lambda: _fetch(ns.seed, ns.gen),
        fetch_stream=lambda: _fetch_stream(ns.seed),
        handlers={OutputMode.INTERACTIVE: lambda ctx: _run_interactive(ctx, ns.seed)},
        description=__doc__,
        prog="life.py",
        help_args=[
            HelpArg("--seed", f"starting pattern: {', '.join(sorted(SEEDS))}", default=DEFAULT_SEED),
            HelpArg("--gen", "generation shown by static output (live plays from 0)", default=str(DEFAULT_GEN)),
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
