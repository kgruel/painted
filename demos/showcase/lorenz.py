#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Lorenz — the butterfly, with time accumulated in the state.

Every demo so far rendered a moment; lorenz renders a *history*. Each
tracer carries its recent trail in the frozen state, and the render ages
it — bright head, fading tail — so the attractor's shape accumulates on
screen from data, not from terminal residue. That's the new concept:
temporal accumulation as just another field.

Two tracers fly the same system from starts 0.01 apart. Chaos does the
rest: their separation — graphed live in the spread row — explodes from
invisible to the attractor's width, which is also the demo's sharpest
law (deterministic divergence under a fixed integrator). The classic
parameters: sigma 10, rho 28, beta 8/3, integrated with RK4.

    uv run demos/showcase/lorenz.py                  # the butterfly, mid-flight
    uv run demos/showcase/lorenz.py --live           # watch it trace
    uv run demos/showcase/lorenz.py --frame 80 -v    # early flight + separation
    uv run demos/showcase/lorenz.py -vv              # bordered, full stats
    uv run demos/showcase/lorenz.py -q               # one-line census
    uv run demos/showcase/lorenz.py --json           # tracers + trails as data
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
    Fidelity,
    Line,
    Span,
    Style,
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


# --- Data: position plus accumulated time ---

P3 = tuple[float, float, float]

_TRAIL_CAP = 360  # positions kept per tracer — the accumulation window
_HISTORY_CAP = 120  # separation samples kept for the sparkline


@dataclass(frozen=True)
class Tracer:
    pos: P3
    trail: tuple[P3, ...]  # most recent last, capped


@dataclass(frozen=True)
class Orbit:
    tracers: tuple[Tracer, ...]
    frame: int
    history: tuple[float, ...]  # tracer separation per frame, capped


# Classic chaotic parameters; the twin starts differ by 0.01 in x —
# under a cell's worth of space, and divergence plays out inside the
# live run's 30 seconds (1e-4 would stay invisible for ~12s of flight).
_SIGMA, _RHO, _BETA = 10.0, 28.0, 8.0 / 3.0
_STARTS: tuple[P3, ...] = ((1.0, 1.0, 20.0), (1.01, 1.0, 20.0))

DEFAULT_FRAME = 400  # static snapshot: trails long enough to read the wings


def seed_orbit() -> Orbit:
    tracers = tuple(Tracer(pos=p, trail=(p,)) for p in _STARTS)
    return Orbit(tracers=tracers, frame=0, history=(_separation(tracers),))


# --- The step: RK4, pure function ---

_DT = 0.01
_SUBSTEPS = 2  # integrator ticks per rendered frame


def _deriv(p: P3) -> P3:
    x, y, z = p
    return (_SIGMA * (y - x), x * (_RHO - z) - y, x * y - _BETA * z)


def _rk4(p: P3, dt: float) -> P3:
    def add(a: P3, b: P3, s: float) -> P3:
        return (a[0] + b[0] * s, a[1] + b[1] * s, a[2] + b[2] * s)

    k1 = _deriv(p)
    k2 = _deriv(add(p, k1, dt / 2))
    k3 = _deriv(add(p, k2, dt / 2))
    k4 = _deriv(add(p, k3, dt))
    return tuple(p[i] + dt / 6 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) for i in range(3))  # type: ignore[return-value]


def step(orbit: Orbit) -> Orbit:
    """One frame: every tracer advances _SUBSTEPS RK4 ticks, trail rides along."""
    tracers = []
    for tr in orbit.tracers:
        pos = tr.pos
        for _ in range(_SUBSTEPS):
            pos = _rk4(pos, _DT)
        tracers.append(Tracer(pos=pos, trail=(*tr.trail, pos)[-_TRAIL_CAP:]))
    tracers = tuple(tracers)
    return replace(
        orbit,
        tracers=tracers,
        frame=orbit.frame + 1,
        history=(*orbit.history, _separation(tracers))[-_HISTORY_CAP:],
    )


def _advance(orbit: Orbit, frames: int) -> Orbit:
    for _ in range(frames):
        orbit = step(orbit)
    return orbit


def _separation(tracers: tuple[Tracer, ...]) -> float:
    a, b = tracers[0].pos, tracers[1].pos
    return math.dist(a, b)


# --- Fetch: snapshot and stream ---


def _fetch(frame: int = DEFAULT_FRAME) -> Orbit:
    """Static snapshot: the twin flight advanced to a fixed frame."""
    return _advance(seed_orbit(), frame)


_FPS = 30
_MAX_FRAMES = 900  # ~30s; the attractor never settles, so the bound is the curtain


async def _fetch_stream(start: int = 0) -> AsyncIterator[Orbit]:
    """Trace at the budget; the live harness gauges its own delivery cost."""
    budget = 1.0 / _FPS
    orbit = _advance(seed_orbit(), start)
    yield orbit
    while orbit.frame < start + _MAX_FRAMES:
        await asyncio.sleep(budget)
        orbit = step(orbit)
        yield orbit


# --- Render helpers ---

_W, _H = 64, 22
# The butterfly lives in the x-z plane: x in about [-20, 20], z in [0, 50].
_X_LO, _X_HI = -22.0, 22.0
_Z_LO, _Z_HI = 0.0, 52.0

# Age carried twice: by glyph and by weight. Index 0 = oldest tail.
_AGE_GLYPHS = ("·", ":", "*", "@")


def _age_style(base: Style, age_idx: int) -> Style:
    if age_idx == 0:
        return base.merge(Style(dim=True))
    if age_idx == len(_AGE_GLYPHS) - 1:
        return base.merge(Style(bold=True))
    return base


def _cell(p: P3) -> tuple[int, int] | None:
    x, _, z = p
    cx = int((x - _X_LO) / (_X_HI - _X_LO) * _W)
    cy = int((_Z_HI - z) / (_Z_HI - _Z_LO) * _H)
    if 0 <= cx < _W and 0 <= cy < _H:
        return cx, cy
    return None


def _grid(orbit: Orbit, width: int) -> Block:
    """Trails projected to the x-z plane; younger points overwrite older."""
    p = current_palette()
    roles = (p.accent, p.warning)  # one hue per tracer — watch them split
    cells: dict[tuple[int, int], tuple[int, int]] = {}  # (x, y) -> (tracer, age_idx)
    for t_idx, tr in enumerate(orbit.tracers):
        n = len(tr.trail)
        for i, pos in enumerate(tr.trail):
            c = _cell(pos)
            if c is None:
                continue
            age_idx = min(len(_AGE_GLYPHS) - 1, (i * len(_AGE_GLYPHS)) // max(1, n))
            prev = cells.get(c)
            if prev is None or age_idx >= prev[1]:
                cells[c] = (t_idx, age_idx)
    rows: list[Block] = []
    for y in range(_H):
        spans: list[Span] = []
        for x in range(_W):
            hit = cells.get((x, y))
            if hit is None:
                spans.append(Span(" ", Style()))
            else:
                t_idx, age_idx = hit
                spans.append(Span(_AGE_GLYPHS[age_idx], _age_style(roles[t_idx], age_idx)))
        rows.append(Line(spans=tuple(spans)).to_block(min(_W, width)))
    return join_vertical(*rows)


def _census(orbit: Orbit) -> Block:
    p = current_palette()
    return join_horizontal(
        Block.text("lorenz", p.accent.merge(Style(bold=True))),
        Block.text(
            f"  frame {orbit.frame:>3}  σ {_SIGMA:.0f}  ρ {_RHO:.0f}  β {_BETA:.2f}"
            f"  Δ {orbit.history[-1]:6.2f}",
            Style(dim=True),
        ),
    )


def _separation_sparkline(orbit: Orbit, width: int) -> Block:
    # Fixed width from frame 0 — pads until history fills it, so the
    # window never widens as samples accumulate.
    spark_w = max(8, width - 13)
    return join_horizontal(
        Block.text("Δ pos ", Style(dim=True)),
        sparkline(list(orbit.history), spark_w, style=current_palette().warning),
        Block.text(f" {orbit.history[-1]:6.2f}", Style(dim=True)),
    )


def _window(orbit: Orbit, width: int | None, *extra: Block) -> Block:
    """The dressed viewing frame: butterfly, census, and any extras.

    Inner width pins to the grid — every row is sized against it, so the
    border never moves no matter what the data rows do. The grid is a raster
    of the field's own domain size (_W) — when no width is offered (a pipe's
    natural sizing), that domain size is the natural inner width, not a
    resurrected terminal-fallback guess.
    """
    w = _W if width is None else min(width - 4, _W)
    rows = [_grid(orbit, w), truncate(_census(orbit), w)]
    rows += [truncate(b, w) for b in extra]
    return border(join_vertical(*rows), title="lorenz", chars=ROUNDED)


# --- Zoom renderers ---


def _render_minimal(orbit: Orbit, width: int | None) -> Block:
    block = _census(orbit)
    return truncate(block, width) if width is not None else block


def _render_summary(orbit: Orbit, width: int | None) -> Block:
    return _window(orbit, width)


def _render_detailed(orbit: Orbit, width: int | None) -> Block:
    w = _W if width is None else min(width - 4, _W)
    return _window(orbit, width, _separation_sparkline(orbit, w))


def _render_full(orbit: Orbit, width: int | None) -> Block:
    w = _W if width is None else min(width - 4, _W)
    head = orbit.tracers[0].pos
    stats = Block.text(
        f"frame {orbit.frame}  ·  head ({head[0]:6.2f}, {head[1]:6.2f}, {head[2]:6.2f})  ·  "
        f"Δ {orbit.history[-1]:.2f}  ·  trail {len(orbit.tracers[0].trail)}/{_TRAIL_CAP}",
        Style(dim=True),
    )
    return _window(orbit, width, _separation_sparkline(orbit, w), stats)


def _render(orbit: Orbit, fidelity: Fidelity, width: int | None) -> Block:
    depth = fidelity.depth
    if depth >= 3:
        return _render_full(orbit, width)
    if depth >= 2:
        return _render_detailed(orbit, width)
    if depth >= 1:
        return _render_summary(orbit, width)
    return _render_minimal(orbit, width)


# --- Entry point ---


def main() -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--frame", type=int, default=DEFAULT_FRAME)
    ns, rest = pre.parse_known_args(sys.argv[1:])

    return run_cli(
        rest,
        renderer=_render,
        fetch=lambda: _fetch(ns.frame),
        fetch_stream=lambda: _fetch_stream(),
        live_delivery="surface",
        live_meter=True,
        description=__doc__,
        prog="lorenz.py",
        help_args=[
            HelpArg(
                "--frame",
                "frame shown by static output (live traces from 0)",
                default=str(DEFAULT_FRAME),
            ),
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
