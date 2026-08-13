#!/usr/bin/env python3
"""Plasma — a colored field, where every cell's color is data.

Life animated glyphs and donut tiered an ASCII ramp through font weight;
plasma's new concept is *per-cell color*: the scene is a smooth scalar
field f(x, y, t) — four interfering sine waves — and each cell's value
picks both a glyph from an intensity ramp and a `Style(fg="#rrggbb")`
from a precomputed gradient. The demo speaks raw truecolor hex; the
*writer* owns fidelity, downsampling per terminal to 256 colors, to 16,
or stripping color entirely — so a pipe still receives the field carried
honestly by the glyph ramp alone.

Color this dense has a cost: consecutive same-colored cells share one
styled span (one SGR sequence on a TTY), so the field's smoothness sets
the style-run load. `-vv` surfaces runs/row — the SGR economics of a
frame, measured in the frame.

    uv run demos/showcase/plasma.py                  # one pose of the field
    uv run demos/showcase/plasma.py --live           # let it swirl
    uv run demos/showcase/plasma.py --frame 200 -v   # later pose + shade legend
    uv run demos/showcase/plasma.py -vv              # bordered, runs/row stats
    uv run demos/showcase/plasma.py -q               # one-line census
    uv run demos/showcase/plasma.py --json           # the pose as data
"""

from __future__ import annotations

import asyncio
import math
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

from painted import (
    Block,
    Fidelity,
    Line,
    Span,
    Style,
    join_horizontal,
    truncate,
    join_vertical,
)
from painted.palette import current_palette

from _harness import ShowcaseArg, plate, showcase_main


# --- Data: the pose is just time ---


@dataclass(frozen=True)
class Plasma:
    frame: int


_T_STEP = 0.06  # field time advanced per frame, radians-ish

DEFAULT_FRAME = 80


def _fetch(frame: int = DEFAULT_FRAME) -> Plasma:
    return Plasma(frame=frame)


_FPS = 30
_MAX_FRAMES = 900  # ~30s; the field never settles, so the bound is the curtain


async def _fetch_stream(start: int = 0) -> AsyncIterator[Plasma]:
    """Swirl at the budget; the live harness gauges its own delivery cost."""
    budget = 1.0 / _FPS
    for frame in range(start, start + _MAX_FRAMES):
        yield Plasma(frame=frame)
        await asyncio.sleep(budget)


# --- The field: four interfering waves, pure f(x, y, t) ---

_W, _H = 64, 22


def _field(x: float, y: float, t: float) -> float:
    """The plasma value at one cell, normalized to [0, 1]."""
    yy = y * 2.0  # character cells are ~2:1 — un-squash before measuring distance
    v = math.sin(x / 9.0 + t)
    v += math.sin((yy + t) / 5.0)
    v += math.sin((x + yy + t) / 11.0)
    # A radial wave from a center that itself orbits — this is what swirls.
    cx = _W / 2 + (_W / 3) * math.sin(t / 3.0)
    cy = _H + _H * math.cos(t / 2.0)  # yy-domain is 0..2*_H
    v += math.sin(math.hypot(x - cx, yy - cy) / 7.0 + t)
    return (v + 4.0) / 8.0


def _sample(pose: Plasma) -> list[list[float]]:
    """The whole field for one pose: _H rows of _W values in [0, 1]."""
    t = pose.frame * _T_STEP
    return [[_field(x, y, t) for x in range(_W)] for y in range(_H)]


# --- Two carriers: a glyph ramp (pipes) and a color ramp (TTYs) ---

_RAMP = " .:-=+*#%@"

# Gradient anchors, low to high intensity. The values are tunable; lerping
# them into _SHADES discrete styles is the point — color computed as data.
_ANCHORS = ("#1c2f9e", "#7a2fbe", "#e84a8a", "#ff8c42", "#ffe66e")
_SHADES = 24


def _lerp_styles(anchors: tuple[str, ...], n: int) -> tuple[Style, ...]:
    rgbs = [tuple(int(a[i : i + 2], 16) for i in (1, 3, 5)) for a in anchors]
    styles = []
    for i in range(n):
        pos = i / (n - 1) * (len(rgbs) - 1)
        j = min(int(pos), len(rgbs) - 2)
        t = pos - j
        r, g, b = (round(rgbs[j][k] + (rgbs[j + 1][k] - rgbs[j][k]) * t) for k in range(3))
        styles.append(Style(fg=f"#{r:02x}{g:02x}{b:02x}"))
    return tuple(styles)


_STYLES = _lerp_styles(_ANCHORS, _SHADES)


def _glyph_idx(v: float) -> int:
    return min(len(_RAMP) - 1, int(v * len(_RAMP)))


def _shade_idx(v: float) -> int:
    return min(_SHADES - 1, int(v * _SHADES))


# --- Render helpers ---


def _grid(pose: Plasma, width: int) -> Block:
    """The field as styled rows: cells sharing a shade share one span."""
    rows: list[Block] = []
    for value_row in _sample(pose):
        spans: list[Span] = []
        run: list[str] = []
        run_shade = _shade_idx(value_row[0])
        for v in (*value_row, None):  # sentinel flushes the last run
            shade = run_shade if v is None else _shade_idx(v)
            if v is not None and shade == run_shade:
                run.append(_RAMP[_glyph_idx(v)])
                continue
            spans.append(Span("".join(run), _STYLES[run_shade]))
            if v is not None:
                run, run_shade = [_RAMP[_glyph_idx(v)]], shade
        rows.append(Line(spans=tuple(spans)).to_block(min(_W, width)))
    return join_vertical(*rows)


def _census(pose: Plasma) -> Block:
    p = current_palette()
    return join_horizontal(
        Block.text("plasma", p.accent.merge(Style(bold=True))),
        Block.text(f"  frame {pose.frame:>3}  t {pose.frame * _T_STEP:6.2f}", Style(dim=True)),
    )


def _legend() -> Block:
    # Both carriers, side by side: the gradient the TTY sees, the ramp a pipe gets.
    spans = [Span("shade ", Style(dim=True))]
    spans += [Span("█", s) for s in _STYLES]
    spans += [Span("  " + _RAMP.strip(), Style(dim=True))]
    return Line(spans=tuple(spans)).to_block(6 + _SHADES + 2 + len(_RAMP.strip()))


def _runs_per_row(pose: Plasma) -> float:
    """Average styled spans per row — the SGR load a TTY pays for this pose."""
    shade_rows = [[_shade_idx(v) for v in row] for row in _sample(pose)]
    runs = sum(1 + sum(1 for a, b in zip(row, row[1:]) if a != b) for row in shade_rows)
    return runs / _H


def _window(pose: Plasma, width: int | None, *extra: Block) -> Block:
    """The dressed viewing frame: field, census, and any extras.

    Inner width pins to the field grid — every row is sized against it, so
    the border never moves no matter what the data rows do. The grid is a
    raster of the field's own domain size (_W) — when no width is offered
    (a pipe's natural sizing), that domain size is the natural inner width,
    not a resurrected terminal-fallback guess.
    """
    w = _W if width is None else min(width - 4, _W)
    rows = [_grid(pose, w), truncate(_census(pose), w)]
    rows += [truncate(b, w) for b in extra]
    return plate(*rows, title="plasma")


# --- Zoom renderers ---


def _render_minimal(pose: Plasma, width: int | None) -> Block:
    block = _census(pose)
    return truncate(block, width) if width is not None else block


def _render_summary(pose: Plasma, width: int | None) -> Block:
    return _window(pose, width)


def _render_detailed(pose: Plasma, width: int | None) -> Block:
    return _window(pose, width, _legend())


def _render_full(pose: Plasma, width: int | None) -> Block:
    field = _sample(pose)
    mean = sum(sum(row) for row in field) / (_W * _H)
    shades = len({_shade_idx(v) for row in field for v in row})
    stats = Block.text(
        f"frame {pose.frame}  ·  mean {mean:.2f}  ·  shades {shades}/{_SHADES}  ·  "
        f"runs/row {_runs_per_row(pose):.1f}",
        Style(dim=True),
    )
    return _window(pose, width, _legend(), stats)


def _render(pose: Plasma, fidelity: Fidelity, width: int | None) -> Block:
    depth = fidelity.depth
    if depth >= 3:
        return _render_full(pose, width)
    if depth >= 2:
        return _render_detailed(pose, width)
    if depth >= 1:
        return _render_summary(pose, width)
    return _render_minimal(pose, width)


# --- Entry point ---


def main() -> int:
    return showcase_main(
        doc=__doc__,
        file=__file__,
        renderer=_render,
        fetch=lambda ns: _fetch(ns.frame),
        fetch_stream=lambda ns: _fetch_stream(),
        args=(
            ShowcaseArg(
                "--frame",
                "pose shown by static output (live swirls from 0)",
                DEFAULT_FRAME,
                type=int,
            ),
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
