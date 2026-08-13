#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Harmonograph — four pendulums drawing in eight-dot terminal cells.

The score is frozen data: two damped oscillators for x, two for y. Their
sum traces one continuous curve, while tiny phase drifts make the figure
breathe without keeping mutable canvas state. The renderer rasterizes that
curve into Braille — eight subpixels carried by one terminal cell — and
painted still composes the result as an ordinary, width-aware ``Block``.

Color-capable destinations receive ink that changes along the stroke.
Unicode-only destinations keep the full Braille geometry without color;
an ASCII destination receives density marks instead. Same score, three
honest carriers, selected from declared render capabilities.

    uv run demos/showcase/harmonograph.py                  # one finished plate
    uv run demos/showcase/harmonograph.py --live           # let the figure breathe
    uv run demos/showcase/harmonograph.py --frame 300 -v   # later phase + score
    uv run demos/showcase/harmonograph.py --stats          # raster facts by name
    uv run demos/showcase/harmonograph.py -vv              # score + raster facts
    uv run demos/showcase/harmonograph.py -q               # one-line census
    uv run demos/showcase/harmonograph.py --json           # the score as data
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache

from painted import (
    Block,
    Fidelity,
    Line,
    ROUNDED,
    Span,
    Style,
    border,
    fit_to_width,
    join_horizontal,
    join_vertical,
    run_cli,
)
from painted.capabilities import current_capabilities
from painted.cli import HelpArg, Tag
from painted.palette import current_palette


# --- Data: a mechanical score, frozen ---


@dataclass(frozen=True)
class Pendulum:
    amplitude: float
    frequency: float
    phase: float
    damping: float
    drift: float  # phase change per rendered frame


@dataclass(frozen=True)
class Score:
    x: tuple[Pendulum, ...]
    y: tuple[Pendulum, ...]


@dataclass(frozen=True)
class Performance:
    frame: int
    score: Score


SCORE = Score(
    x=(
        Pendulum(amplitude=0.58, frequency=3.000, phase=0.00, damping=0.0030, drift=0.0021),
        Pendulum(amplitude=0.42, frequency=3.013, phase=1.57, damping=0.0050, drift=-0.0013),
    ),
    y=(
        Pendulum(amplitude=0.60, frequency=2.000, phase=0.18, damping=0.0035, drift=0.0011),
        Pendulum(amplitude=0.40, frequency=2.017, phase=1.32, damping=0.0045, drift=-0.0023),
    ),
)

DEFAULT_FRAME = 180


def _fetch(frame: int = DEFAULT_FRAME) -> Performance:
    return Performance(frame=frame, score=SCORE)


_FPS = 30
_MAX_FRAMES = 900  # ~30s, then the curtain falls


async def _fetch_stream(start: int = 0, frames: int = _MAX_FRAMES) -> AsyncIterator[Performance]:
    budget = 1.0 / _FPS
    for frame in range(start, start + frames):
        yield Performance(frame=frame, score=SCORE)
        await asyncio.sleep(budget)


# --- Curve: four damped oscillators, one pure point function ---


def _axis(voices: tuple[Pendulum, ...], t: float, frame: int) -> float:
    return sum(
        p.amplitude
        * math.sin(p.frequency * t + p.phase + p.drift * frame)
        * math.exp(-p.damping * t)
        for p in voices
    )


def _point(performance: Performance, t: float) -> tuple[float, float]:
    score = performance.score
    return _axis(score.x, t, performance.frame), _axis(score.y, t, performance.frame)


_SAMPLES = 3200
_T_END = 118.0
_DOT_ROWS = 88  # 22 terminal rows × four Braille dots
_NATURAL_COLUMNS = 64


def _curve(performance: Performance) -> tuple[tuple[float, float], ...]:
    return tuple(_point(performance, i * _T_END / (_SAMPLES - 1)) for i in range(_SAMPLES))


# --- Raster: points become Braille bits; collisions become measurable ink ---


@dataclass(frozen=True)
class Raster:
    masks: tuple[tuple[int, ...], ...]
    shades: tuple[tuple[int, ...], ...]
    plotted: int
    collisions: int


_BRAILLE_BITS = (
    (0x01, 0x08),
    (0x02, 0x10),
    (0x04, 0x20),
    (0x40, 0x80),
)


def _line_pixels(x0: int, y0: int, x1: int, y1: int) -> tuple[tuple[int, int], ...]:
    """Integer line rasterization keeps adjacent curve samples connected."""
    points: list[tuple[int, int]] = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx + dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return tuple(points)
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


@lru_cache(maxsize=12)
def _raster(performance: Performance, columns: int, rows: int = _DOT_ROWS // 4) -> Raster:
    columns = max(1, columns)
    rows = max(1, rows)
    dot_w, dot_h = columns * 2, rows * 4
    masks = [[0 for _ in range(columns)] for _ in range(rows)]
    shades = [[0 for _ in range(columns)] for _ in range(rows)]
    plotted = collisions = 0

    x_extent = sum(abs(p.amplitude) for p in performance.score.x)
    y_extent = sum(abs(p.amplitude) for p in performance.score.y)

    def project(point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        px = round((0.5 + 0.47 * x / x_extent) * (dot_w - 1))
        py = round((0.5 - 0.47 * y / y_extent) * (dot_h - 1))
        return min(dot_w - 1, max(0, px)), min(dot_h - 1, max(0, py))

    curve = _curve(performance)
    previous = project(curve[0])
    for index, point in enumerate(curve[1:], start=1):
        current = project(point)
        shade = min(_INK_SHADES - 1, index * _INK_SHADES // len(curve))
        for px, py in _line_pixels(*previous, *current):
            cell_x, dot_x = divmod(px, 2)
            cell_y, dot_y = divmod(py, 4)
            bit = _BRAILLE_BITS[dot_y][dot_x]
            if masks[cell_y][cell_x] & bit:
                collisions += 1
            else:
                masks[cell_y][cell_x] |= bit
                plotted += 1
            # The newest passage owns the ink at a crossing, like wet ink.
            shades[cell_y][cell_x] = shade
        previous = current

    return Raster(
        masks=tuple(tuple(row) for row in masks),
        shades=tuple(tuple(row) for row in shades),
        plotted=plotted,
        collisions=collisions,
    )


# --- Carriers: truecolor ink, color-free Braille, strict ASCII density ---


_INK_ANCHORS = ("#50e3ff", "#7868ff", "#d65cff", "#ff5c9a", "#ffc857")
_INK_SHADES = 24
_ASCII_DENSITY = " .:+*#@"


def _gradient(anchors: tuple[str, ...], count: int) -> tuple[Style, ...]:
    rgbs = [tuple(int(color[i : i + 2], 16) for i in (1, 3, 5)) for color in anchors]
    styles: list[Style] = []
    for index in range(count):
        position = index / (count - 1) * (len(rgbs) - 1)
        left = min(int(position), len(rgbs) - 2)
        mix = position - left
        rgb = tuple(
            round(rgbs[left][c] + (rgbs[left + 1][c] - rgbs[left][c]) * mix) for c in range(3)
        )
        styles.append(Style(fg=f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"))
    return tuple(styles)


_INK_STYLES = _gradient(_INK_ANCHORS, _INK_SHADES)


def _carrier(mask: int, *, glyph: bool) -> str:
    if mask == 0:
        return " "
    if glyph:
        return chr(0x2800 + mask)
    density = math.ceil(mask.bit_count() * (len(_ASCII_DENSITY) - 1) / 8)
    return _ASCII_DENSITY[density]


def _ink_style(mask: int, shade: int, *, color: bool) -> Style:
    if mask == 0:
        return Style()
    if color:
        return _INK_STYLES[shade]
    accent = current_palette().accent
    if mask.bit_count() <= 2:
        return accent.merge(Style(dim=True))
    if mask.bit_count() >= 6:
        return accent.merge(Style(bold=True))
    return accent


def _plate(performance: Performance, columns: int) -> Block:
    raster = _raster(performance, columns)
    caps = current_capabilities()
    rows: list[Block] = []
    for masks, shades in zip(raster.masks, raster.shades):
        spans: list[Span] = []
        run: list[str] = []
        run_style: Style | None = None
        for mask, shade in (*zip(masks, shades), (None, None)):
            if mask is not None:
                style = _ink_style(mask, shade, color=caps.color)
                char = _carrier(mask, glyph=caps.glyph)
                if run_style is None or style == run_style:
                    run.append(char)
                    run_style = style
                    continue
            if run:
                spans.append(Span("".join(run), run_style or Style()))
            if mask is not None:
                run, run_style = [char], style
        rows.append(Line(spans=tuple(spans)).to_block(columns))
    return join_vertical(*rows)


# --- Composition and fidelity ---


def _census(performance: Performance) -> Block:
    p = current_palette()
    return join_horizontal(
        Block.text("harmonograph", p.accent.merge(Style(bold=True))),
        Block.text(
            f"  frame {performance.frame:>3}  pendulums 4  samples {_SAMPLES}",
            Style(dim=True),
        ),
    )


def _score(performance: Performance) -> Block:
    p = current_palette()
    spans: list[Span] = [Span("score  ", Style(dim=True))]
    for axis, voices, style in (
        ("x", performance.score.x, p.accent),
        ("y", performance.score.y, p.warning),
    ):
        spans.append(Span(f"{axis} ", style.merge(Style(bold=True))))
        spans.append(Span(" + ".join(f"{voice.frequency:.3f}Hz" for voice in voices), style))
        spans.append(Span("   ", Style()))
    return Line(spans=tuple(spans)).to_block(52)


def _stats(performance: Performance, columns: int) -> Block:
    raster = _raster(performance, columns)
    occupied = sum(mask != 0 for row in raster.masks for mask in row)
    cells = columns * len(raster.masks)
    carrier = "braille" if current_capabilities().glyph else "ascii"
    return Block.text(
        f"ink {raster.plotted}  ·  cross {raster.collisions}  ·  "
        f"cells {occupied}/{cells} {occupied / cells:.0%}  ·  carrier {carrier}",
        Style(dim=True),
    )


def _window(performance: Performance, width: int | None, *extra: Block) -> Block:
    # A supplied width is an exact allocation. The natural plate remains a
    # compact 64 columns; an offered terminal grows or shrinks its subpixel grid.
    columns = _NATURAL_COLUMNS if width is None else max(1, width - 2)
    rows = [_plate(performance, columns), fit_to_width(_census(performance), columns)]
    rows.extend(fit_to_width(block, columns) for block in extra)
    window = border(join_vertical(*rows), title="harmonograph", chars=ROUNDED)
    return window if width is None else fit_to_width(window, width)


_TAGS = [
    Tag("score", "Show the four-pendulum score", implied_at=2),
    Tag("stats", "Show raster occupancy and carrier facts", implied_at=3),
]


def _render(performance: Performance, fidelity: Fidelity, width: int | None) -> Block:
    depth = fidelity.depth
    extra: list[Block] = []
    if depth >= 2 or fidelity.shows("score"):
        extra.append(_score(performance))
    if fidelity.shows("stats"):
        columns = _NATURAL_COLUMNS if width is None else max(1, width - 2)
        extra.append(_stats(performance, columns))
    if depth >= 1:
        return _window(performance, width, *extra)

    rows = [_census(performance), *extra]
    block = join_vertical(*rows)
    return block if width is None else fit_to_width(block, width)


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
        prog="harmonograph.py",
        tags=_TAGS,
        help_args=[
            HelpArg(
                "--frame",
                "phase shown by static output (live breathes from 0)",
                default=str(DEFAULT_FRAME),
            ),
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
