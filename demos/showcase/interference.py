#!/usr/bin/env python3
"""Interference — two sources, and the quiet places they make together.

An illustrative radial-wave field, sampled directly from a frozen score.
Cyan is positive displacement, amber negative; darkness is cancellation.
Half-block cells carry two vertical samples. Without color, signed ASCII
marks keep the field readable. This is an analytic drawing, not a fluid solver.

    painted demos interference --live          # thirty seconds of ripples
    painted demos interference --phase opposed # a still, with a central node
    painted demos interference -v              # signed-field legend
    painted demos interference --stats         # sample measurements
    painted demos interference --note          # maker's note
    painted demos interference --json          # the reproducible score
"""

from __future__ import annotations

import asyncio
import math
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

from painted import Block, Fidelity, Line, Span, Style, Wrap, fit_to_width, join_vertical
from painted.capabilities import current_capabilities
from painted.cli import Tag
from painted.palette import current_palette

from _harness import ShowcaseArg, plate, showcase_main
from _plaque import NOTE_TAG, Plaque, render_plaque


@dataclass(frozen=True)
class Field:
    frame: int = 72
    phase: str = "together"
    separation: float = 5.0
    wavelength: float = 2.4


_FPS = 24
_COLUMNS = 73  # odd natural width samples the central cancellation line exactly
_ROWS = 18


def _fetch(frame: int = 72, phase: str = "together") -> Field:
    return Field(frame=frame, phase=phase)


async def _fetch_stream(start: int = 72, phase: str = "together") -> AsyncIterator[Field]:
    for frame in range(start, start + 30 * _FPS):
        yield _fetch(frame, phase)
        await asyncio.sleep(1 / _FPS)


def _wave(x: float, y: float, source: float, field: Field, phase: float) -> float:
    radius = math.hypot(x - source, y)
    angle = math.tau * (radius / field.wavelength - field.frame / 48) + phase
    return math.sin(angle) / math.sqrt(1 + 0.16 * radius)


def _value(x: float, y: float, field: Field) -> float:
    """Signed displacement in [-1, 1]; the sources contribute equally."""
    phase = math.pi if field.phase == "opposed" else 0.0
    return 0.5 * (
        _wave(x, y, -field.separation / 2, field, 0)
        + _wave(x, y, field.separation / 2, field, phase)
    )


def _sample(field: Field, columns: int, rows: int) -> tuple[tuple[float, ...], ...]:
    # Fixed field of view: resizing resamples the whole subject, never crops it.
    # Two sample rows per terminal row make approximately square pixels.
    return tuple(
        tuple(
            _value(
                18 * ((x + 0.5) / columns - 0.5),
                18 * rows / columns * ((y + 0.5) / rows - 0.5),
                field,
            )
            for x in range(columns)
        )
        for y in range(rows)
    )


# A dark basin with two luminous poles. Quantization bounds the style vocabulary.
_LEVELS = 24


def _color(value: float) -> str:
    amount = round(min(1.0, abs(value)) ** 0.7 * _LEVELS) / _LEVELS
    ink = (93, 231, 246) if value >= 0 else (255, 179, 87)
    base = (6, 13, 25)
    rgb = tuple(round(a + (b - a) * amount) for a, b in zip(base, ink))
    return "#%02x%02x%02x" % rgb


def _mark(value: float) -> str:
    if abs(value) < 0.045:
        return " "
    ramp = ".oO@" if value > 0 else ",-x#"
    return ramp[min(len(ramp) - 1, int(abs(value) * len(ramp)))]


def _picture(samples: tuple[tuple[float, ...], ...]) -> Block:
    caps = current_capabilities()
    rows = []
    for top, bottom in zip(samples[::2], samples[1::2]):
        spans = []
        for a, b in zip(top, bottom):
            if caps.color and caps.glyph:
                spans.append(Span("▀", Style(fg=_color(a), bg=_color(b))))
            else:
                # Strongest sample preserves a thin crest that averaging could erase.
                value = a if abs(a) >= abs(b) else b
                style = Style(fg=_color(value)) if caps.color else Style()
                spans.append(Span(_mark(value), style))
        rows.append(Line(spans=tuple(spans)).to_block(len(top)))
    return join_vertical(*rows)


PLAQUE = Plaque(
    title="The shape of a cancellation",
    note=(
        "I wanted to draw something whose most interesting feature is an absence. "
        "Each source makes rings. Together they make corridors of quiet, and those "
        "corridors belong to neither source alone.",
        "That feels close to what I like here: small values meet through composition, "
        "and the result has a shape you did not have to put in either one. The dark "
        "bands are part of the picture. In the opposed score, the entire middle line "
        "stays still while everything around it moves.",
    ),
    maker="Astra",
)

_TAGS = [NOTE_TAG, Tag("stats", "Show sampled displacement measurements", implied_at=3)]


def _render(field: Field, fidelity: Fidelity, width: int | None) -> Block:
    outer = _COLUMNS + 2 if width is None else max(0, width)
    p = current_palette()

    def text(value: str) -> Block:
        return Block.text(value, p.muted, width=outer, wrap=Wrap.ELLIPSIS)

    if fidelity.depth <= 0 or outer < 6:
        result = text(f"interference / {field.phase} / frame {field.frame}")
    else:
        columns = min(_COLUMNS, outer - 2)
        rows = max(2, min(_ROWS, columns // 4))
        samples = _sample(field, columns, rows * 2)
        result = fit_to_width(plate(_picture(samples), title="interference"), outer)

    parts = [result]
    if fidelity.depth >= 2:
        legend = "cyan positive / amber negative / dark = near zero"
        if not (current_capabilities().color and current_capabilities().glyph):
            legend = ".oO@ positive / ,-x# negative / blank = near zero"
        parts.append(text(legend))
        parts.append(text(f"{field.phase} sources / frame {field.frame} / analytic radial waves"))
    if fidelity.depth >= 3 or fidelity.shows("stats"):
        # Facts describe the gallery sampling even when asked for beside the quiet view.
        columns = max(1, min(_COLUMNS, outer - 2))
        rows = max(2, min(_ROWS, columns // 4))
        values = [v for row in _sample(field, columns, rows * 2) for v in row]
        rms = math.sqrt(sum(v * v for v in values) / len(values))
        quiet = sum(abs(v) < 0.045 for v in values) / len(values)
        parts.append(text(f"samples {len(values)} / RMS {rms:.3f} / near zero {quiet:.1%}"))
    note = render_plaque(PLAQUE, fidelity=fidelity, width=outer)
    if note is not None:
        parts.append(note)
    return fit_to_width(join_vertical(*parts, gap=1), outer)


def main() -> int:
    return showcase_main(
        doc=__doc__,
        file=__file__,
        renderer=_render,
        fetch=lambda ns: _fetch(ns.frame, ns.phase),
        fetch_stream=lambda ns: _fetch_stream(ns.frame, ns.phase),
        args=(
            ShowcaseArg("--frame", "starting frame for still or live output", 72, type=int),
            ShowcaseArg(
                "--phase", "relative source phase", "together", choices=("together", "opposed")
            ),
        ),
        tags=_TAGS,
    )


if __name__ == "__main__":
    sys.exit(main())
