#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""donut.c — a spinning torus, state reduced to a frame counter.

The companion piece to life.py in the churn pair: Life's changes scatter
across a sparse population, the donut sweeps continuous shading through a
solid band of cells. (Measured glyph churn is deceptively similar — slow
rotation means gentle frames; cranking _A_STEP is the stress knob.)
State is a single integer — the frame number — and
the whole scene is a pure function of it: rotation angles derive from the
counter, a z-buffered projection shades the torus through the classic
luminance ramp (.,-~:;=!*#$@). The ramp is pure ASCII, so a pipe receives
the authentic 1997 artifact; a TTY additionally gets the shading tiered
through dim/normal/bold spans.

    uv run demos/patterns/donut.py                   # one frame, mid-spin
    uv run demos/patterns/donut.py --live            # spin it
    uv run demos/patterns/donut.py --frame 200 -v    # later pose + shading legend
    uv run demos/patterns/donut.py -vv               # bordered, full stats
    uv run demos/patterns/donut.py -q                # one-line pose census
    uv run demos/patterns/donut.py --json            # the pose as data
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from time import perf_counter

from painted import (
    Block,
    CliContext,
    Line,
    Span,
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


# --- Data: the pose is just time ---


@dataclass(frozen=True)
class Spin:
    frame: int
    # Observed render+write cost per frame, ms — measured by the stream at its
    # yield boundary, empty for static poses. The scene is still a pure
    # function of the frame; the gauge is data riding alongside.
    frame_ms: tuple[float, ...] = ()


_A_STEP, _B_STEP = 0.07, 0.03  # radians of rotation per frame, per axis


def _angles(spin: Spin) -> tuple[float, float]:
    return spin.frame * _A_STEP, spin.frame * _B_STEP


DEFAULT_FRAME = 60


def _fetch(frame: int = DEFAULT_FRAME) -> Spin:
    return Spin(frame=frame)


_FPS = 30
_MAX_FRAMES = 900  # ~30s; the torus never settles, so the bound is the curtain
_METER_CAP = 60  # frame-cost samples kept for the meter


async def _fetch_stream(start: int = 0) -> AsyncIterator[Spin]:
    """Spin at the budget; the yield-to-resume gap is the harness's frame cost."""
    budget = 1.0 / _FPS
    spin = Spin(frame=start)
    cost = 0.0
    for frame in range(start, start + _MAX_FRAMES):
        spin = replace(
            spin, frame=frame, frame_ms=(*spin.frame_ms, cost * 1000)[-_METER_CAP:] if frame > start else ()
        )
        t0 = perf_counter()
        yield spin
        cost = perf_counter() - t0
        await asyncio.sleep(max(0.0, budget - cost))


# --- The projection: donut.c, faithfully ---

_W, _H = 64, 24
_R1, _R2, _K2 = 1.0, 2.0, 5.0
_XSCALE, _YSCALE = 24.0, 12.0  # 2:1 — character-cell aspect baked into projection

_RAMP = ".,-~:;=!*#$@"

# Surface sampling tables, precomputed once (donut.c's theta 0.07 / phi 0.02 steps).
_THETA = [(math.cos(t), math.sin(t)) for t in (i * 0.07 for i in range(90))]
_PHI = [(math.cos(p), math.sin(p)) for p in (i * 0.02 for i in range(315))]


def _project(spin: Spin) -> list[list[int]]:
    """Z-buffered luminance indices for one pose: -1 = empty, 0-11 = ramp index."""
    a, b = _angles(spin)
    ca, sa = math.cos(a), math.sin(a)
    cb, sb = math.cos(b), math.sin(b)
    shade = [[-1] * _W for _ in range(_H)]
    zbuf = [[0.0] * _W for _ in range(_H)]
    for ct, st in _THETA:
        cx, cy = _R2 + _R1 * ct, _R1 * st  # the tube circle, pre-revolution
        for cp, sp in _PHI:
            x3 = cx * (cb * cp + sa * sb * sp) - cy * ca * sb
            y3 = cx * (sb * cp - sa * cb * sp) + cy * ca * cb
            ooz = 1.0 / (_K2 + ca * cx * sp + cy * sa)
            xp = int(_W / 2 + _XSCALE * ooz * x3)
            yp = int(_H / 2 - _YSCALE * ooz * y3)
            if not (0 <= xp < _W and 0 <= yp < _H):
                continue
            lum = cp * ct * sb - ca * ct * sp - sa * st + cb * (ca * st - ct * sa * sp)
            if lum > 0 and ooz > zbuf[yp][xp]:
                zbuf[yp][xp] = ooz
                shade[yp][xp] = min(11, int(lum * 8))
    return shade


# --- Render helpers ---


def _tier(idx: int) -> Style:
    """Ramp index → style: shading carried twice, by glyph and by weight."""
    accent = current_palette().accent
    if idx >= 8:
        return accent.merge(Style(bold=True))
    if idx <= 3:
        return accent.merge(Style(dim=True))
    return accent


def _torus(spin: Spin, width: int) -> Block:
    rows: list[Block] = []
    for shade_row in _project(spin):
        spans: list[Span] = []
        run, run_idx = [], shade_row[0]
        for idx in (*shade_row, None):  # sentinel flushes the last run
            if idx is not None and (idx == run_idx or (idx < 0 and run_idx < 0)):
                run.append(" " if idx < 0 else _RAMP[idx])
                continue
            if run:
                spans.append(
                    Span("".join(run), Style() if run_idx < 0 else _tier(run_idx))
                )
            if idx is not None:
                run, run_idx = [" " if idx < 0 else _RAMP[idx]], idx
        rows.append(Line(spans=tuple(spans)).to_block(min(_W, width)))
    return join_vertical(*rows)


def _census(spin: Spin) -> Block:
    a, b = _angles(spin)
    p = current_palette()
    return join_horizontal(
        Block.text("donut", p.accent.merge(Style(bold=True))),
        Block.text(f"  frame {spin.frame:>3}  A {a:5.2f}  B {b:5.2f}", Style(dim=True)),
    )


def _legend() -> Block:
    spans = [Span("shade ", Style(dim=True))]
    spans += [Span(ch, _tier(i)) for i, ch in enumerate(_RAMP)]
    return Line(spans=tuple(spans)).to_block(len(_RAMP) + 6)


def _lit(shade: list[list[int]]) -> int:
    return sum(1 for row in shade for idx in row if idx >= 0)


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


def _window(spin: Spin, width: int, *extra: Block) -> Block:
    """The dressed viewing frame: torus, census, live meter, and any extras.

    Inner width pins to the torus grid — every row is sized against it, so
    the border never moves no matter what the data rows do.
    """
    w = min(width - 4, _W)
    rows = [_torus(spin, w), truncate(_census(spin), w)]
    meter = _meter(spin.frame_ms, _FPS, w)
    if meter is not None:
        rows.append(truncate(meter, w))
    rows += [truncate(b, w) for b in extra]
    return border(join_vertical(*rows), title="donut.c", chars=ROUNDED)


# --- Zoom renderers ---


def _render_minimal(spin: Spin, width: int) -> Block:
    return truncate(_census(spin), width)


def _render_summary(spin: Spin, width: int) -> Block:
    return _window(spin, width)


def _render_detailed(spin: Spin, width: int) -> Block:
    return _window(spin, width, _legend())


def _render_full(spin: Spin, width: int) -> Block:
    shade = _project(spin)
    lit = _lit(shade)
    a, b = _angles(spin)
    stats = Block.text(
        f"frame {spin.frame}  ·  A {a:.2f}  B {b:.2f}  ·  "
        f"lit {lit}  ·  coverage {lit / (_W * _H):.0%}",
        Style(dim=True),
    )
    return _window(spin, width, _legend(), stats)


def _render(ctx: CliContext, spin: Spin) -> Block:
    if ctx.zoom == Zoom.MINIMAL:
        return _render_minimal(spin, ctx.width)
    if ctx.zoom == Zoom.DETAILED:
        return _render_detailed(spin, ctx.width)
    if ctx.zoom == Zoom.FULL:
        return _render_full(spin, ctx.width)
    return _render_summary(spin, ctx.width)


# --- Entry point ---


def main() -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--frame", type=int, default=DEFAULT_FRAME)
    ns, rest = pre.parse_known_args(sys.argv[1:])

    return run_cli(
        rest,
        render=_render,
        fetch=lambda: _fetch(ns.frame),
        fetch_stream=lambda: _fetch_stream(),
        live_delivery="surface",
        description=__doc__,
        prog="donut.py",
        help_args=[
            HelpArg(
                "--frame",
                "pose shown by static output (live spins from 0)",
                default=str(DEFAULT_FRAME),
            ),
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
