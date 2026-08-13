#!/usr/bin/env python3
"""Fire — the Doom PSX flame, with randomness as frozen data.

Plasma was a pure function of time; fire needs *chance* — each cell cools
and drifts by a random amount as heat propagates upward. The new concept
is how a frozen-state world gets randomness without losing its laws: a
seeded LCG whose state is carried IN the data. `step(fire)` is still a
pure function — same Fire in, same Fire out — because the generator's
state is just another field. Same seed, same inferno, every run; law
tests stay deterministic with no mocking.

The bottom row is fuel (always max heat); every other cell pulls from
the row below it with a random sideways drift and a random decay. Heat
maps through a fire gradient (per-cell truecolor, downsampled by the
writer) and an intensity glyph ramp, so a pipe gets the flame in pure
ASCII.

    uv run demos/showcase/fire.py                    # one pose, steady burn
    uv run demos/showcase/fire.py --live             # let it burn
    uv run demos/showcase/fire.py --seed 13 -v       # different chance, legend
    uv run demos/showcase/fire.py --frame 20 -vv     # early ignition, full stats
    uv run demos/showcase/fire.py -q                 # one-line census
    uv run demos/showcase/fire.py --json             # the heat field as data
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

from painted import (
    Block,
    Fidelity,
    Line,
    Span,
    Style,
    join_horizontal,
    join_vertical,
    truncate,
)
from painted.palette import current_palette

from _harness import ShowcaseArg, plate, showcase_main


# --- Randomness as data: a seeded LCG threaded through the state ---

_LCG_A, _LCG_C, _LCG_M = 1664525, 1013904223, 1 << 32


def _lcg(state: int) -> int:
    """One LCG step. The caller owns the state — no hidden generator."""
    return (_LCG_A * state + _LCG_C) % _LCG_M


# --- Data: a frozen heat field ---

_W, _H = 64, 22
_LEVELS = 24  # heat 0 (cold) .. _LEVELS-1 (fuel)

Heat = tuple[int, ...]  # row-major _W * _H, JSON-friendly


@dataclass(frozen=True)
class Fire:
    heat: Heat
    rng: int  # LCG state — randomness carried as data
    frame: int
    seed: int


DEFAULT_SEED = 7
DEFAULT_FRAME = 80  # static snapshot: past ignition, into the steady burn


def ignite(seed: int = DEFAULT_SEED) -> Fire:
    """Frame 0: everything cold except the fuel row."""
    heat = (0,) * (_W * (_H - 1)) + (_LEVELS - 1,) * _W
    return Fire(heat=heat, rng=_lcg(seed), frame=0, seed=seed)


# --- The step: pure propagation, chance included ---


def step(fire: Fire) -> Fire:
    """One tick: every cell pulls from below with random drift and decay.

    Pure despite the randomness — the LCG state rides in, advances per
    cell, and rides out. The fuel row is rewritten to max every tick.
    """
    old = fire.heat
    rng = fire.rng
    new = [0] * (_W * _H)
    drift = (-1, 0, 1, 0)  # symmetric sideways flicker
    for y in range(_H - 1):
        below = (y + 1) * _W
        row = y * _W
        for x in range(_W):
            rng = _lcg(rng)
            r = (rng >> 16) & 0xF  # four fair bits per cell
            sx = (x + drift[r & 3]) % _W
            # Decay 0..3 (avg 1.5) — tuned so the flame burns out around
            # two-thirds of the grid instead of hitting the ceiling.
            new[row + x] = max(0, old[below + sx] - (r >> 2))
    new[(_H - 1) * _W :] = [_LEVELS - 1] * _W
    return replace(fire, heat=tuple(new), rng=rng, frame=fire.frame + 1)


def _advance(fire: Fire, frames: int) -> Fire:
    for _ in range(frames):
        fire = step(fire)
    return fire


# --- Fetch: snapshot and stream ---


def _fetch(seed: int = DEFAULT_SEED, frame: int = DEFAULT_FRAME) -> Fire:
    """Static snapshot: the seed burned to a fixed, reproducible frame."""
    return _advance(ignite(seed), frame)


_FPS = 30
_MAX_FRAMES = 900  # ~30s; constant fuel never settles, so the bound is the curtain


async def _fetch_stream(seed: int = DEFAULT_SEED) -> AsyncIterator[Fire]:
    """Burn at the budget; the live harness gauges its own delivery cost."""
    budget = 1.0 / _FPS
    fire = ignite(seed)
    yield fire
    while fire.frame < _MAX_FRAMES:
        await asyncio.sleep(budget)
        fire = step(fire)
        yield fire


# --- Two carriers: a glyph ramp (pipes) and a fire gradient (TTYs) ---

_RAMP = " .:-=+*#%@"

# Gradient anchors, cold to fuel: ember black, deep red, flame orange,
# yellow, near-white. Second demo to lerp a gradient (plasma was first) —
# a third wants it, the helper graduates to views.
_ANCHORS = ("#07070a", "#5c0a0a", "#c43b0e", "#f6962e", "#fff1a8")


def _lerp_styles(anchors: tuple[str, ...], n: int) -> tuple[Style, ...]:
    rgbs = [tuple(int(a[i : i + 2], 16) for i in (1, 3, 5)) for a in anchors]
    styles = []
    for i in range(n):
        pos = i / (n - 1) * (len(rgbs) - 1)
        j = min(int(pos), len(rgbs) - 2)
        r, g, b = (round(rgbs[j][k] + (rgbs[j + 1][k] - rgbs[j][k]) * (pos - j)) for k in range(3))
        styles.append(Style(fg=f"#{r:02x}{g:02x}{b:02x}"))
    return tuple(styles)


_STYLES = _lerp_styles(_ANCHORS, _LEVELS)


def _glyph(heat: int) -> str:
    return _RAMP[min(len(_RAMP) - 1, heat * len(_RAMP) // _LEVELS)]


# --- Render helpers ---


def _grid(fire: Fire, width: int) -> Block:
    """The heat field as styled rows: cells sharing a level share one span."""
    rows: list[Block] = []
    for y in range(_H):
        row = fire.heat[y * _W : (y + 1) * _W]
        spans: list[Span] = []
        run: list[str] = []
        run_heat = row[0]
        for h in (*row, None):  # sentinel flushes the last run
            if h is not None and h == run_heat:
                run.append(_glyph(h))
                continue
            spans.append(Span("".join(run), _STYLES[run_heat]))
            if h is not None:
                run, run_heat = [_glyph(h)], h
        rows.append(Line(spans=tuple(spans)).to_block(min(_W, width)))
    return join_vertical(*rows)


def _census(fire: Fire) -> Block:
    p = current_palette()
    return join_horizontal(
        Block.text("fire", p.accent.merge(Style(bold=True))),
        Block.text(f"  frame {fire.frame:>3}  seed {fire.seed}", Style(dim=True)),
    )


def _legend() -> Block:
    spans = [Span("heat ", Style(dim=True))]
    spans += [Span("█", s) for s in _STYLES]
    spans += [Span("  " + _RAMP.strip(), Style(dim=True))]
    return Line(spans=tuple(spans)).to_block(5 + _LEVELS + 2 + len(_RAMP.strip()))


def _flame_height(fire: Fire) -> int:
    """Rows from the fuel up to the highest cell still meaningfully hot."""
    for y in range(_H):
        if any(h >= _LEVELS // 4 for h in fire.heat[y * _W : (y + 1) * _W]):
            return _H - y
    return 0


def _window(fire: Fire, width: int | None, *extra: Block) -> Block:
    """The dressed viewing frame: field, census, and any extras.

    Inner width pins to the grid — every row is sized against it, so the
    border never moves no matter what the data rows do. The grid is a
    raster of the field's own domain size (_W) — when no width is offered
    (a pipe's natural sizing), that domain size is the natural inner width,
    not a resurrected terminal-fallback guess.
    """
    w = _W if width is None else min(width - 4, _W)
    rows = [_grid(fire, w), truncate(_census(fire), w)]
    rows += [truncate(b, w) for b in extra]
    return plate(*rows, title="fire")


# --- Zoom renderers ---


def _render_minimal(fire: Fire, width: int | None) -> Block:
    block = _census(fire)
    return truncate(block, width) if width is not None else block


def _render_summary(fire: Fire, width: int | None) -> Block:
    return _window(fire, width)


def _render_detailed(fire: Fire, width: int | None) -> Block:
    return _window(fire, width, _legend())


def _render_full(fire: Fire, width: int | None) -> Block:
    lit = sum(1 for h in fire.heat if h > 0)
    mean = sum(fire.heat) / len(fire.heat)
    stats = Block.text(
        f"frame {fire.frame}  ·  seed {fire.seed}  ·  mean heat {mean:.1f}  ·  "
        f"lit {lit / (_W * _H):.0%}  ·  flame height {_flame_height(fire)}/{_H}",
        Style(dim=True),
    )
    return _window(fire, width, _legend(), stats)


def _render(fire: Fire, fidelity: Fidelity, width: int | None) -> Block:
    depth = fidelity.depth
    if depth >= 3:
        return _render_full(fire, width)
    if depth >= 2:
        return _render_detailed(fire, width)
    if depth >= 1:
        return _render_summary(fire, width)
    return _render_minimal(fire, width)


# --- Entry point ---


def main() -> int:
    return showcase_main(
        doc=__doc__,
        file=__file__,
        renderer=_render,
        fetch=lambda ns: _fetch(ns.seed, ns.frame),
        fetch_stream=lambda ns: _fetch_stream(ns.seed),
        args=(
            ShowcaseArg("--seed", "LCG seed — same seed, same inferno", DEFAULT_SEED, type=int),
            ShowcaseArg(
                "--frame",
                "frame shown by static output (live burns from 0)",
                DEFAULT_FRAME,
                type=int,
            ),
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
