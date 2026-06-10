#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Boids — agents in a continuous world, projected onto cells.

Life and fire lived on the grid; boids don't. The flock flies through a
continuous toroidal plane — positions and velocities are floats — and
only the *projection* quantizes them into half-block pixels. That's the
new concept: the cell buffer is a viewport onto continuous state, not
the state itself.

The other lesson is emergence you can test. Each boid follows three
local rules — cohesion (drift toward neighbors), alignment (match their
heading), separation (don't crowd) — and flocking appears without a
flock rule. The laws pin each force with constructed cases (a crowded
pair repels, a surrounded boid turns with traffic, a loner flies
straight) and the demo shows emergence as data: the spread sparkline
falls as the flock finds itself. Initial scatter comes from the seeded
LCG settled by fire.py — randomness as frozen data, same seed, same
flight.

    uv run demos/patterns/boids.py                   # one pose, mid-flight
    uv run demos/patterns/boids.py --live            # watch them flock
    uv run demos/patterns/boids.py --seed 13 -v      # new scatter + spread spark
    uv run demos/patterns/boids.py --frame 30 -vv    # early chaos, full stats
    uv run demos/patterns/boids.py -q                # one-line census
    uv run demos/patterns/boids.py --json            # the flock as data
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

from painted import (
    Block,
    CliContext,
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


# --- Randomness as data (the pattern fire.py settled) ---

_LCG_A, _LCG_C, _LCG_M = 1664525, 1013904223, 1 << 32


def _lcg(state: int) -> int:
    return (_LCG_A * state + _LCG_C) % _LCG_M


def _rand01(state: int) -> tuple[float, int]:
    """One uniform float in [0, 1) and the advanced LCG state."""
    state = _lcg(state)
    return (state >> 8) / (1 << 24), state


# --- Data: a frozen flock in a continuous world ---

_W, _GH = 64.0, 44.0  # continuous torus; renders 64 x 22 via half-blocks
_N = 40
_HISTORY_CAP = 120  # spread samples kept for the sparkline

BoidT = tuple[float, float, float, float]  # x, y, vx, vy — JSON-friendly


@dataclass(frozen=True)
class Flock:
    boids: tuple[BoidT, ...]
    frame: int
    seed: int
    history: tuple[float, ...]  # spread per frame, capped


DEFAULT_SEED = 7
DEFAULT_FRAME = 150  # static snapshot: deep enough for flocks to have formed


def seed_flock(seed: int = DEFAULT_SEED) -> Flock:
    """Frame 0: boids scattered uniformly, headings uniform, speed at cruise."""
    rng = _lcg(seed)
    boids: list[BoidT] = []
    for _ in range(_N):
        u, rng = _rand01(rng)
        v, rng = _rand01(rng)
        h, rng = _rand01(rng)
        angle = h * math.tau
        speed = (_V_MIN + _V_MAX) / 2
        boids.append((u * _W, v * _GH, math.cos(angle) * speed, math.sin(angle) * speed))
    flock = Flock(boids=tuple(boids), frame=0, seed=seed, history=())
    return replace(flock, history=(_spread(flock.boids),))


# --- The step: three local rules, pure function ---

_R_NEIGH = 10.0  # how far a boid can see
_R_SEP = 2.5  # personal space
_W_COH, _W_ALI, _W_SEP = 0.006, 0.06, 0.12
_V_MIN, _V_MAX = 0.35, 1.1  # cells per frame — boids can't hover or teleport


def _delta(a: float, b: float, span: float) -> float:
    """Shortest signed distance from a to b on a circle of the given span."""
    return (b - a + span / 2) % span - span / 2


def step(flock: Flock) -> Flock:
    """One tick: cohesion + alignment + separation, then clamp and wrap."""
    boids = flock.boids
    new: list[BoidT] = []
    for i, (x, y, vx, vy) in enumerate(boids):
        coh_x = coh_y = ali_x = ali_y = sep_x = sep_y = 0.0
        n = 0
        for j, (ox, oy, ovx, ovy) in enumerate(boids):
            if i == j:
                continue
            dx, dy = _delta(x, ox, _W), _delta(y, oy, _GH)
            d2 = dx * dx + dy * dy
            if d2 > _R_NEIGH * _R_NEIGH:
                continue
            n += 1
            coh_x += dx
            coh_y += dy
            ali_x += ovx
            ali_y += ovy
            if 0.0 < d2 < _R_SEP * _R_SEP:
                sep_x -= dx / d2  # push away, harder when closer
                sep_y -= dy / d2
        if n:
            vx += _W_COH * (coh_x / n) + _W_ALI * (ali_x / n - vx) + _W_SEP * sep_x
            vy += _W_COH * (coh_y / n) + _W_ALI * (ali_y / n - vy) + _W_SEP * sep_y
        speed = math.hypot(vx, vy)
        if speed < 1e-9:  # forces cancelled exactly — resume on the old heading
            vx, vy = boids[i][2], boids[i][3]
            speed = math.hypot(vx, vy)
        clamped = min(_V_MAX, max(_V_MIN, speed))
        vx, vy = vx / speed * clamped, vy / speed * clamped
        new.append(((x + vx) % _W, (y + vy) % _GH, vx, vy))
    spread = _spread(tuple(new))
    return replace(
        flock,
        boids=tuple(new),
        frame=flock.frame + 1,
        history=(*flock.history, spread)[-_HISTORY_CAP:],
    )


def _advance(flock: Flock, frames: int) -> Flock:
    for _ in range(frames):
        flock = step(flock)
    return flock


def _spread(boids: tuple[BoidT, ...]) -> float:
    """Mean distance to the flock's toroidal centroid — emergence as a number.

    The centroid of points on a torus is found per axis by the circular
    mean: map positions to angles, average the unit vectors, read the
    angle back. Falls as local rules pull the flock together.
    """

    def axis_center(values: list[float], span: float) -> float:
        s = sum(math.sin(v / span * math.tau) for v in values)
        c = sum(math.cos(v / span * math.tau) for v in values)
        return (math.atan2(s, c) % math.tau) / math.tau * span

    cx = axis_center([b[0] for b in boids], _W)
    cy = axis_center([b[1] for b in boids], _GH)
    return sum(math.hypot(_delta(b[0], cx, _W), _delta(b[1], cy, _GH)) for b in boids) / len(boids)


# --- Fetch: snapshot and stream ---


def _fetch(seed: int = DEFAULT_SEED, frame: int = DEFAULT_FRAME) -> Flock:
    """Static snapshot: the scatter flown to a fixed, reproducible frame."""
    return _advance(seed_flock(seed), frame)


_FPS = 30
_MAX_FRAMES = 900  # ~30s; the flock never lands, so the bound is the curtain


async def _fetch_stream(seed: int = DEFAULT_SEED) -> AsyncIterator[Flock]:
    """Fly at the budget; the live harness gauges its own delivery cost."""
    budget = 1.0 / _FPS
    flock = seed_flock(seed)
    yield flock
    while flock.frame < _MAX_FRAMES:
        await asyncio.sleep(budget)
        flock = step(flock)
        yield flock


# --- Render helpers ---

_GLYPHS = (" ", "▀", "▄", "█")  # indexed by upper-occupied | lower-occupied << 1
_COLS, _ROWS = int(_W), int(_GH)


def _grid(flock: Flock, width: int) -> Block:
    """The projection: continuous positions quantized into half-block pixels."""
    live = {(int(x) % _COLS, int(y) % _ROWS) for x, y, _, _ in flock.boids}
    style = current_palette().accent
    rows: list[Block] = []
    for ty in range(_ROWS // 2):
        chars = []
        for x in range(_COLS):
            idx = ((x, 2 * ty) in live) | (((x, 2 * ty + 1) in live) << 1)
            chars.append(_GLYPHS[idx])
        rows.append(Block.text("".join(chars), style))
    return truncate(join_vertical(*rows), width)


def _census(flock: Flock) -> Block:
    p = current_palette()
    return join_horizontal(
        Block.text("boids", p.accent.merge(Style(bold=True))),
        Block.text(
            f"  frame {flock.frame:>3}  flock {len(flock.boids)}  seed {flock.seed}",
            Style(dim=True),
        ),
    )


def _spread_sparkline(flock: Flock, width: int) -> Block:
    # Fixed width from frame 0 — pads until history fills it, so the
    # window never widens as samples accumulate.
    spark_w = max(8, width - 14)
    return join_horizontal(
        Block.text("spread ", Style(dim=True)),
        sparkline(list(flock.history), spark_w, style=current_palette().success),
        Block.text(f" {flock.history[-1]:5.1f}", Style(dim=True)),
    )


def _window(flock: Flock, width: int, *extra: Block) -> Block:
    """The dressed viewing frame: flock, census, and any extras.

    Inner width pins to the grid — every row is sized against it, so the
    border never moves no matter what the data rows do.
    """
    w = min(width - 4, _COLS)
    rows = [_grid(flock, w), truncate(_census(flock), w)]
    rows += [truncate(b, w) for b in extra]
    return border(join_vertical(*rows), title="boids", chars=ROUNDED)


# --- Zoom renderers ---


def _render_minimal(flock: Flock, width: int) -> Block:
    return truncate(_census(flock), width)


def _render_summary(flock: Flock, width: int) -> Block:
    return _window(flock, width)


def _render_detailed(flock: Flock, width: int) -> Block:
    w = min(width - 4, _COLS)
    return _window(flock, width, _spread_sparkline(flock, w))


def _render_full(flock: Flock, width: int) -> Block:
    w = min(width - 4, _COLS)
    mean_speed = sum(math.hypot(vx, vy) for _, _, vx, vy in flock.boids) / len(flock.boids)
    stats = Block.text(
        f"frame {flock.frame}  ·  seed {flock.seed}  ·  spread {flock.history[-1]:.1f}  ·  "
        f"mean speed {mean_speed:.2f}  ·  clamp [{_V_MIN}, {_V_MAX}]",
        Style(dim=True),
    )
    return _window(flock, width, _spread_sparkline(flock, w), stats)


def _render(ctx: CliContext, flock: Flock) -> Block:
    if ctx.zoom == Zoom.MINIMAL:
        return _render_minimal(flock, ctx.width)
    if ctx.zoom == Zoom.DETAILED:
        return _render_detailed(flock, ctx.width)
    if ctx.zoom == Zoom.FULL:
        return _render_full(flock, ctx.width)
    return _render_summary(flock, ctx.width)


# --- Entry point ---


def main() -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--seed", type=int, default=DEFAULT_SEED)
    pre.add_argument("--frame", type=int, default=DEFAULT_FRAME)
    ns, rest = pre.parse_known_args(sys.argv[1:])

    return run_cli(
        rest,
        render=_render,
        fetch=lambda: _fetch(ns.seed, ns.frame),
        fetch_stream=lambda: _fetch_stream(ns.seed),
        live_delivery="surface",
        live_meter=True,
        description=__doc__,
        prog="boids.py",
        help_args=[
            HelpArg("--seed", "LCG seed — same seed, same flight", default=str(DEFAULT_SEED)),
            HelpArg(
                "--frame",
                "frame shown by static output (live flies from 0)",
                default=str(DEFAULT_FRAME),
            ),
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
