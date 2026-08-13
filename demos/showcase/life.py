#!/usr/bin/env python3
"""Conway's Life — a pure pattern, animated by the harness.

The world is frozen data, the step is a pure function, the render is a pure
function — time comes from the CLI harness, not the demo. `fetch_stream`
yields successive generations and InPlaceRenderer repaints only the cells
that changed; the same render function serves the static snapshot, the live
animation, and the plain-text pipe. Two grid rows share one terminal row via
half-block glyphs (▀ ▄ █), so the picture stays square-ish without color
tricks — it survives `| cat` untouched.

    uv run demos/showcase/life.py                    # snapshot at generation 100
    uv run demos/showcase/life.py --live             # animate from the seed
    uv run demos/showcase/life.py --seed acorn -v    # grid + population sparkline
    uv run demos/showcase/life.py --gen 300 -vv      # bordered, full stats
    uv run demos/showcase/life.py -q                 # one-line census
    uv run demos/showcase/life.py --json             # the grid as data
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

from painted import (
    Block,
    Fidelity,
    Style,
    join_horizontal,
    join_vertical,
    truncate,
)
from painted.palette import current_palette
from painted.views import sparkline

from _harness import ShowcaseArg, plate, showcase_main


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


async def _fetch_stream(seed: str = DEFAULT_SEED) -> AsyncIterator[LifeWorld]:
    """Animate from the seed; stop on death, stasis, or short oscillation.

    The stream only paces the show — delivery cost is measured and shown
    by the live harness itself (its LiveMeter row under the frame), since
    only the delivery mechanism can observe what delivery costs.
    """
    budget = 1.0 / _FPS
    world = seed_world(seed)
    yield world
    prev: Cells = ()
    prev2: Cells = ()
    while world.generation < _MAX_GENS:
        await asyncio.sleep(budget)
        prev, prev2 = world.cells, prev
        world = step(world)
        yield world
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


def _window(world: LifeWorld, width: int | None, *extra: Block) -> Block:
    """The dressed viewing frame: grid, census, and any extras.

    Inner width pins to the grid — every row is sized against it, so the
    border never moves no matter what the data rows do. The grid is a
    raster of the world's own domain size (world.cols) — when no width is
    offered (a pipe's natural sizing), that domain size is the natural
    inner width, not a resurrected terminal-fallback guess.
    """
    w = world.cols if width is None else min(width - 4, world.cols)
    rows = [_grid(world, w), truncate(_census(world), w)]
    rows += [truncate(b, w) for b in extra]
    return plate(*rows, title="Conway's Life")


# --- Zoom renderers ---


def _render_minimal(world: LifeWorld, width: int | None) -> Block:
    block = _census(world)
    return truncate(block, width) if width is not None else block


def _render_summary(world: LifeWorld, width: int | None) -> Block:
    return _window(world, width)


def _render_detailed(world: LifeWorld, width: int | None) -> Block:
    w = world.cols if width is None else min(width - 4, world.cols)
    return _window(world, width, _pop_sparkline(world, w))


def _render_full(world: LifeWorld, width: int | None) -> Block:
    w = world.cols if width is None else min(width - 4, world.cols)
    peak = max(world.history)
    density = len(world.cells) / (world.cols * world.rows)
    stats = Block.text(
        f"seed {world.seed}  ·  gen {world.generation:>3}  ·  "
        f"pop {len(world.cells):>3}  ·  peak {peak:>3}  ·  density {density:.1%}",
        Style(dim=True),
    )
    return _window(world, width, _pop_sparkline(world, w), stats)


def _render(world: LifeWorld, fidelity: Fidelity, width: int | None) -> Block:
    depth = fidelity.depth
    if depth >= 3:
        return _render_full(world, width)
    if depth >= 2:
        return _render_detailed(world, width)
    if depth >= 1:
        return _render_summary(world, width)
    return _render_minimal(world, width)


# --- Entry point ---


def main() -> int:
    return showcase_main(
        doc=__doc__,
        file=__file__,
        renderer=_render,
        fetch=lambda ns: _fetch(ns.seed, ns.gen),
        fetch_stream=lambda ns: _fetch_stream(ns.seed),
        args=(
            ShowcaseArg(
                "--seed",
                f"starting pattern: {', '.join(sorted(SEEDS))}",
                DEFAULT_SEED,
                choices=tuple(sorted(SEEDS)),
            ),
            ShowcaseArg(
                "--gen",
                "generation shown by static output (live plays from 0)",
                DEFAULT_GEN,
                type=int,
            ),
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
