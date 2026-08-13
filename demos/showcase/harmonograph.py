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

    uv run demos/showcase/harmonograph.py                  # gallery plate, nothing else
    uv run demos/showcase/harmonograph.py --live           # let the figure breathe
    uv run demos/showcase/harmonograph.py --note           # + maker's note
    uv run demos/showcase/harmonograph.py -vv              # + score and raster facts
    uv run demos/showcase/harmonograph.py --score          # the score by name
    uv run demos/showcase/harmonograph.py --stats          # raster facts by name
    uv run demos/showcase/harmonograph.py -q               # one-line microplate
    uv run demos/showcase/harmonograph.py --json           # the score as data
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from functools import lru_cache

from painted import (
    Block,
    Fidelity,
    Line,
    ROUNDED,
    Span,
    Style,
    Wrap,
    border,
    fit_to_width,
    join_horizontal,
    join_vertical,
    run_cli,
)
from painted.capabilities import current_capabilities
from painted.cli import HelpArg, Tag
from painted.core.doc import Def, Defs, Doc, Prose, Section, doc_lens
from painted.palette import current_palette

from _plaque import NOTE_TAG


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


def _plate(performance: Performance, columns: int, cell_rows: int = _DOT_ROWS // 4) -> Block:
    raster = _raster(performance, columns, cell_rows)
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


# --- Composition: microplate, gallery plate, annotated plate ---


_MICRO_NATURAL_WIDTH = 42
_RESPONSIVE_BREAKPOINT = 96  # 64-column plate + gap + 30-column annotation


def _micro_parts(performance: Performance, width: int | None) -> tuple[str, int, str, int]:
    """Label, plot columns, suffix, and exact outer width for the quiet row."""
    target = _MICRO_NATURAL_WIDTH if width is None else max(0, width)
    if target <= 0:
        return "", 0, "", 0
    label = "harmonograph " if target >= 28 else ("h " if target >= 8 else "")
    suffix = f"  f{performance.frame}" if target >= 18 else ""
    columns = max(0, target - len(label) - len(suffix))
    return label, columns, suffix, target


def _microplate(performance: Performance, width: int | None) -> Block:
    """One row: x and y each occupy one dot-column of every Braille cell."""
    label, columns, suffix, target = _micro_parts(performance, width)
    if target == 0:
        return Block.empty(0, 1)
    p = current_palette()
    parts: list[Block] = []
    if label:
        parts.append(Block.text(label, p.accent.merge(Style(bold=True))))
    if columns:
        masks: list[int] = []
        for column in range(columns):
            t = column * 8.0 / max(1, columns - 1)
            x, y = _point(performance, t)
            dot_x = min(3, max(0, round((0.5 - 0.45 * x) * 3)))
            dot_y = min(3, max(0, round((0.5 - 0.45 * y) * 3)))
            masks.append(_BRAILLE_BITS[dot_x][0] | _BRAILLE_BITS[dot_y][1])
        caps = current_capabilities()
        spans = tuple(
            Span(
                _carrier(mask, glyph=caps.glyph),
                _ink_style(
                    mask,
                    min(_INK_SHADES - 1, column * _INK_SHADES // len(masks)),
                    color=caps.color,
                ),
            )
            for column, mask in enumerate(masks)
        )
        parts.append(Line(spans=spans).to_block(columns))
    if suffix:
        parts.append(Block.text(suffix, Style(dim=True)))
    if not parts:  # a width too small for the labelled signature
        parts.append(Block.text("h", p.accent.merge(Style(bold=True))))
    return fit_to_width(join_horizontal(*parts), target)


def _gallery(performance: Performance, width: int | None) -> Block:
    """The default exhibit: 22 rows of ink and its frame — exactly 24 rows."""
    outer_width = _NATURAL_COLUMNS + 2 if width is None else max(0, width)
    columns = max(1, outer_width - 2)
    gallery = border(_plate(performance, columns), title="harmonograph", chars=ROUNDED)
    return gallery if width is None else fit_to_width(gallery, outer_width)


_NOTE = (
    "I wanted a subject where the terminal was not impersonating another canvas. "
    "A Braille cell is already an eight-point plotter, so painted's smallest unit "
    "becomes both canvas and ink."
)
_NOTE_2 = (
    "Four simple oscillators supply the complexity. Painted composes the plate, "
    "adapts it to the offered width, and chooses an honest carrier for each destination."
)


def _carrier_name() -> str:
    caps = current_capabilities()
    if not caps.glyph:
        return "ASCII density"
    return "truecolor Braille" if caps.color else "Braille"


def _score_defs(performance: Performance) -> Defs:
    x0, x1 = performance.score.x
    y0, y1 = performance.score.y
    return Defs(
        (
            Def(
                "x",
                f"{x0.frequency:.3f} Hz + {x1.frequency:.3f} Hz",
                detail=(
                    f"amplitude {x0.amplitude:.2f}/{x1.amplitude:.2f}; "
                    f"damping {x0.damping:.4f}/{x1.damping:.4f}; "
                    f"drift {x0.drift:+.4f}/{x1.drift:+.4f}"
                ),
            ),
            Def(
                "y",
                f"{y0.frequency:.3f} Hz + {y1.frequency:.3f} Hz",
                detail=(
                    f"amplitude {y0.amplitude:.2f}/{y1.amplitude:.2f}; "
                    f"damping {y0.damping:.4f}/{y1.damping:.4f}; "
                    f"drift {y0.drift:+.4f}/{y1.drift:+.4f}"
                ),
            ),
        )
    )


def _raster_defs(performance: Performance, columns: int, rows: int) -> Defs:
    raster = _raster(performance, max(1, columns), max(1, rows))
    occupied = sum(mask != 0 for row in raster.masks for mask in row)
    cells = max(1, columns) * max(1, rows)
    return Defs(
        (
            Def("ink", f"{raster.plotted} unique dots", detail=f"{_SAMPLES} joined samples"),
            Def("crossings", str(raster.collisions), detail="newest passage owns the ink"),
            Def("occupancy", f"{occupied}/{cells} cells · {occupied / cells:.0%}"),
            Def("carrier", _carrier_name()),
        )
    )


def _annotation(
    performance: Performance,
    fidelity: Fidelity,
    width: int,
    *,
    note: bool,
    score: bool,
    stats: bool,
    raster_columns: int,
    raster_rows: int,
) -> Block:
    if width < 24:
        named = [
            name
            for name, visible in (("maker note", note), ("score", score), ("raster facts", stats))
            if visible
        ]
        return Block.text(
            "details: " + ", ".join(named),
            Style(dim=True),
            width=width,
            wrap=Wrap.ELLIPSIS,
        )
    body: list[Prose | Section] = []
    if note:
        body.extend((Prose(_NOTE), Prose(_NOTE_2), Prose("— Sol")))
    if score:
        body.append(Section("Score", body=(_score_defs(performance),)))
    if stats:
        body.append(
            Section(
                "Raster",
                body=(_raster_defs(performance, raster_columns, raster_rows),),
            )
        )
    title = "Why this one" if note else "Inside the plate"
    # An explicitly named facet at MINIMAL still deserves its summaries. Lift
    # the doc's local density floor without changing the renderer's Fidelity.
    doc_fidelity = replace(fidelity, depth=max(1, fidelity.depth))
    return doc_lens(Doc(title, tuple(body)), fidelity=doc_fidelity, width=width)


def _annotated(
    performance: Performance,
    fidelity: Fidelity,
    width: int | None,
    *,
    note: bool,
    score: bool,
    stats: bool,
) -> Block:
    outer_width = _NATURAL_COLUMNS + 2 if width is None else max(0, width)
    if width is not None and outer_width >= _RESPONSIVE_BREAKPOINT:
        side_width = min(40, max(30, outer_width - 68))
        art_width = outer_width - 2 - side_width
        gallery = _gallery(performance, art_width)
        annotation = _annotation(
            performance,
            fidelity,
            side_width,
            note=note,
            score=score,
            stats=stats,
            raster_columns=max(1, art_width - 2),
            raster_rows=_DOT_ROWS // 4,
        )
        return fit_to_width(join_horizontal(gallery, annotation, gap=2), outer_width)

    gallery = _gallery(performance, width)
    annotation = _annotation(
        performance,
        fidelity,
        outer_width,
        note=note,
        score=score,
        stats=stats,
        raster_columns=max(1, outer_width - 2),
        raster_rows=_DOT_ROWS // 4,
    )
    return fit_to_width(join_vertical(gallery, annotation, gap=1), outer_width)


# --- Fidelity: signature → gallery → annotation → full record ---


# The gallery reading put the maker's note at -v, where wall text follows the
# picture. The ruling went the other way and applies to every showcase: depth is
# anonymous detail about the *subject*, and who made a thing is not more detail
# about it. NOTE_TAG carries that decision, so it cannot drift back one demo at
# a time. The rest of the register — signature, gallery, annotation, full record
# — is unchanged; only the rung the note answers to moved.
_TAGS = [
    NOTE_TAG,
    Tag("score", "Show the four-pendulum score", implied_at=3),
    Tag("stats", "Show raster occupancy and carrier facts", implied_at=3),
]


def _render(performance: Performance, fidelity: Fidelity, width: int | None) -> Block:
    depth = fidelity.depth
    # Named-only: no depth branch here, or the note would arrive at -v anyway
    # and the shared Tag would be a decoration over a live disagreement.
    note = fidelity.shows("note")
    score = depth >= 3 or fidelity.shows("score")
    stats = depth >= 3 or fidelity.shows("stats")

    if depth <= 0:
        micro = _microplate(performance, width)
        if not (note or score or stats):
            return micro
        outer_width = _MICRO_NATURAL_WIDTH if width is None else max(0, width)
        _label, columns, _suffix, _target = _micro_parts(performance, width)
        annotation = _annotation(
            performance,
            fidelity,
            outer_width,
            note=note,
            score=score,
            stats=stats,
            raster_columns=max(1, columns),
            raster_rows=1,
        )
        return fit_to_width(join_vertical(micro, annotation, gap=1), outer_width)

    if note or score or stats:
        return _annotated(
            performance,
            fidelity,
            width,
            note=note,
            score=score,
            stats=stats,
        )
    return _gallery(performance, width)


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
