#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Mandelbrot — escape time, and an honest black.

The classic renderer paints every cell that outlives the iteration cap
black and calls it "the set". Two different facts wear that one color: a
cell *proved* to be in the set — the main cardioid and the period-2 bulb
have closed-form membership tests — and a cell that merely outlasted the
budget. Membership is only semi-decidable: escape is provable, staying is
not, so the second kind is not a cell we haven't gotten to yet. It is the
answer, and the answer is "unknown".

Three states, then, not two — and the color derives from that declaration
rather than from a hardcoded ramp. A `Vocabulary` binds `escaped` /
`interior` / `unresolved` to roles, and every carrier resolves through
`mark_style`: the truecolor half-blocks, the `--proof` lens, the ASCII
fallback, the census. Hue carries what is *known* (cool = proved, amber =
unproved); luminance within the escaped band carries escape time. The
unknown is the one warm thing on screen, because it is the one thing the
picture cannot stand behind.

The live descent holds the budget fixed at 80 iterations, so the unresolved
band grows as the view falls into the boundary — 3% of the frame at the
opening, 32% at 1800x — and the census counts it the whole way down. The
stream's last yield sets `settled`, spending 5x the budget on the same pose
through the same pure trace: one field changed, and the unknown collapses
to 2%. Where raymarch's settle buys smoothness, this one buys knowledge —
and never all of it. Zoom deep enough and the cardioid proof stops reaching
the view at all: past ~500x there is no proved interior on screen, and the
legend says so by counting zero.

    uv run demos/showcase/mandelbrot.py                       # a TTY streams the descent
    uv run demos/showcase/mandelbrot.py --static              # one settled portrait
    uv run demos/showcase/mandelbrot.py --static --frame 750  # a deeper pose
    uv run demos/showcase/mandelbrot.py --proof               # color by what is proved
    uv run demos/showcase/mandelbrot.py -v                    # + the status legend
    uv run demos/showcase/mandelbrot.py -vv                   # + trace internals
    uv run demos/showcase/mandelbrot.py -q                    # one-line census
    uv run demos/showcase/mandelbrot.py --json                # the view as data
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from bisect import bisect_left
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache

from painted import (
    Block,
    Fidelity,
    Line,
    Role,
    Span,
    Style,
    Vocabulary,
    border,
    join_horizontal,
    join_vertical,
    mark_style,
    run_cli,
    truncate,
    use_vocabularies,
    ROUNDED,
)
from painted.capabilities import current_capabilities
from painted.cli import HelpArg, Tag
from painted.palette import current_palette


# --- Data: a pose is a frame plus how much it may spend ---


@dataclass(frozen=True)
class View:
    frame: int
    settled: bool = False  # False = live budget, True = the settled portrait


DEFAULT_FRAME = 400  # 28x — deep enough to read, shallow enough to hold all three states


def _fetch(frame: int = DEFAULT_FRAME) -> View:
    return View(frame=frame, settled=True)  # a static pose is always the portrait


_FPS = 30
_MAX_FRAMES = 900  # ~30s of descent, then the pose settles


async def _fetch_stream(start: int = 0, frames: int = _MAX_FRAMES) -> AsyncIterator[View]:
    """Descend at the budget, then settle: the last yield asks for knowledge."""
    budget = 1.0 / _FPS
    last = start
    for frame in range(start, start + frames):
        last = frame
        yield View(frame=frame)
        await asyncio.sleep(budget)
    yield View(frame=last, settled=True)


# --- The declared vocabulary: what a cell's color is allowed to mean ---

# Deliberately unordered: these are three *kinds* of answer, not three
# degrees of one. `escaped` and `interior` are proofs (of divergence, of
# membership); `unresolved` is the absence of either within the budget.
# Ranking them would invent a comparison the mathematics doesn't have.
#
# Roles are namespaced (`mandel-`) because the demo suite loads every module
# into one process: a bare `escaped` role would collide with any other demo
# that declared the same name under a different style.
_ESCAPED_HEX = "#76c4c4"  # the escape ramp's mid stop — one source, below
_INTERIOR_HEX = "#3a2a55"  # violet: far enough off the ramp's blue floor to read
_UNRESOLVED_HEX = "#e8a33d"

MEMBERSHIP = Vocabulary(
    "membership",
    values=("escaped", "interior", "unresolved"),
    roles={
        "escaped": Role("mandel-escaped", Style(fg=_ESCAPED_HEX)),
        "interior": Role("mandel-interior", Style(fg=_INTERIOR_HEX)),
        "unresolved": Role("mandel-unresolved", Style(fg=_UNRESOLVED_HEX, bold=True)),
    },
)

ESCAPED, INTERIOR, UNRESOLVED = 0, 1, 2
_STATUS_NAMES = ("escaped", "interior", "unresolved")


# --- The classifier: two proofs and an admission ---

_BAILOUT = 4.0  # |z|^2; once |z| > 2 the orbit provably diverges


def proved_interior(x: float, y: float) -> bool:
    """Closed-form membership: the main cardioid or the period-2 bulb.

    Both are exact — a point satisfying either is in the set, no iteration
    required. They are also *incomplete*: the smaller bulbs and the
    filaments have no such test, so points there stay unresolved however
    long the budget runs. That incompleteness is the demo's subject, not a
    defect to paper over.
    """
    q = (x - 0.25) ** 2 + y * y
    if q * (q + (x - 0.25)) <= 0.25 * y * y:
        return True
    return (x + 1.0) ** 2 + y * y <= 0.0625


def classify(x: float, y: float, budget: int) -> tuple[int, float]:
    """One cell's status and, when it escaped, its smooth escape time.

    The fractional part refines the integer step: bailing at |z|^2 > 4 puts
    log2(log2|z|) in (0, 1], so `nu` lands in [k, k+1) — a continuous
    coordinate inside the step, which is what keeps the gradient from
    banding. Returns nu = -1.0 for the two non-escaping statuses; they have
    no escape time, and inventing one would be the same lie as the black.
    """
    if proved_interior(x, y):
        return INTERIOR, -1.0
    zx = zy = 0.0
    for k in range(budget):
        zx2, zy2 = zx * zx, zy * zy
        if zx2 + zy2 > _BAILOUT:
            nu = k + 1.0 - math.log(math.log(math.sqrt(zx2 + zy2)) / math.log(2.0)) / math.log(2.0)
            return ESCAPED, nu
        zx, zy = zx2 - zy2 + x, 2.0 * zx * zy + y
    return UNRESOLVED, -1.0


# --- The descent: where the view is, and what it may spend ---

_W, _H = 64, 22  # cells; the half-block carrier makes the sample grid _W x 2*_H
_PX_W, _PX_H = _W, 2 * _H
_ASPECT = _PX_H / _PX_W  # half-pixels are square, so the window is not

# Seahorse valley — the classic descent, and a good one for this demo: the
# cardioid proof covers the opening frames and abandons the deep ones.
_TARGET = (-0.743643887037151, 0.13182590420533)
_OPEN = (-0.6, 0.0, 3.2)  # the whole set, centered
_END_ZOOM = 1800.0  # where a fixed budget still resolves ~2/3 of the frame
_RATE = math.log(_END_ZOOM) / _MAX_FRAMES
_PAN_FRAMES = 240.0  # the center eases to the target while the span shrinks

_LIVE_BUDGET = 80
_SETTLE_BUDGET = 400  # 5x: what one frame at rest can afford that 30fps cannot


def window_at(frame: int) -> tuple[float, float, float]:
    """Center and span for a frame — pure, so any pose is reachable."""
    x0, y0, span0 = _OPEN
    t = min(1.0, frame / _PAN_FRAMES)
    ease = t * t * (3.0 - 2.0 * t)
    return (
        x0 + (_TARGET[0] - x0) * ease,
        y0 + (_TARGET[1] - y0) * ease,
        span0 * math.exp(-_RATE * frame),
    )


def budget_of(view: View) -> int:
    return _SETTLE_BUDGET if view.settled else _LIVE_BUDGET


# --- The trace ---


@dataclass(frozen=True)
class Trace:
    rows: tuple[tuple[tuple[int, float], ...], ...]  # (status, nu) per half-pixel
    counts: tuple[int, int, int]  # cells per status, indexed by the status ints
    iterations: int  # what the frame actually spent
    budget: int
    span: float
    escape_times: tuple[float, ...]  # every escaped cell's nu, sorted

    def rank(self, nu: float) -> float:
        """Where `nu` falls among *this frame's* escaped cells, in [0, 1).

        The gradient is a rank, not a duration. Absolute escape times pile up
        against the low end — a handful of boundary-hugging cells set a max
        two orders of magnitude above the median, and a linear ramp against
        it renders every interesting level set the same color. Ranking
        spreads the ramp over the cells actually present, which is why the
        picture keeps its structure all the way down. The claim the color
        makes is therefore comparative and frame-local: *slower than this
        fraction of what escaped here*.
        """
        if not self.escape_times:
            return 0.0
        return bisect_left(self.escape_times, nu) / len(self.escape_times)


@lru_cache(maxsize=4)
def trace(view: View) -> Trace:
    """Classify every half-pixel of one pose. Pure in `view` — hence cached."""
    cx, cy, span = window_at(view.frame)
    budget = budget_of(view)
    left, top = cx - span / 2.0, cy + span * _ASPECT / 2.0
    dx, dy = span / _PX_W, span * _ASPECT / _PX_H
    rows: list[tuple[tuple[int, float], ...]] = []
    counts = [0, 0, 0]
    iterations = 0
    escape_times: list[float] = []
    for py in range(_PX_H):
        y = top - (py + 0.5) * dy
        row: list[tuple[int, float]] = []
        for px in range(_PX_W):
            status, nu = classify(left + (px + 0.5) * dx, y, budget)
            counts[status] += 1
            if status == ESCAPED:
                iterations += int(nu) + 1
                escape_times.append(nu)
            elif status == UNRESOLVED:
                iterations += budget  # the whole budget, spent proving nothing
            row.append((status, nu))
        rows.append(tuple(row))
    escape_times.sort()
    return Trace(
        rows=tuple(rows),
        counts=(counts[0], counts[1], counts[2]),
        iterations=iterations,
        budget=budget,
        span=span,
        escape_times=tuple(escape_times),
    )


# --- Color: hue is the status, luminance is the escape time ---

# Cool only, by design. Every warm pixel in the frame is an unproved one,
# so the eye finds the unknown without reading the legend.
_RAMP = (
    (8, 10, 28),
    (26, 58, 102),
    (44, 118, 150),
    (118, 196, 196),  # == _ESCAPED_HEX, the status color for the flat lens
    (206, 240, 236),
)

_RGB = tuple[int, int, int]


def _ramp_rgb(t: float) -> _RGB:
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    pos = t * (len(_RAMP) - 1)
    i = min(int(pos), len(_RAMP) - 2)
    f = pos - i
    a, b = _RAMP[i], _RAMP[i + 1]
    return (
        int(a[0] + (b[0] - a[0]) * f),
        int(a[1] + (b[1] - a[1]) * f),
        int(a[2] + (b[2] - a[2]) * f),
    )


def _mark_rgb(status: int) -> _RGB:
    """The status color, taken from the declaration rather than restated here.

    A theme may re-tint any declared role; a role re-tinted to a *named*
    color has no hex to read, so the fallback is the ramp's dark end — the
    picture stays honest about status by hue even when it cannot read one.
    """
    fg = mark_style("membership", _STATUS_NAMES[status]).fg
    if isinstance(fg, str) and fg.startswith("#") and len(fg) == 7:
        return (int(fg[1:3], 16), int(fg[3:5], 16), int(fg[5:7], 16))
    return _RAMP[0]


def _pixel_rgb(status: int, rank: float, flat: bool) -> _RGB:
    """One sample's color. `flat` is the --proof lens: status, nothing else."""
    if status != ESCAPED or flat:
        return _mark_rgb(status)
    return _ramp_rgb(rank)


# --- Carriers ---

# Escape time as a glyph ramp for the no-color path; the two non-escaping
# statuses get glyphs of their own, because a pipe has no hue to carry them.
_GLYPH_RAMP = " .,-~:;=!*"
_GLYPH_INTERIOR = "@"
_GLYPH_UNRESOLVED = "?"


def _grid_color(view: View, width: int, flat: bool) -> Block:
    """Half-block truecolor: two samples per cell, fg over bg."""
    t = trace(view)
    rows: list[Block] = []
    for cy in range(_H):
        top, bot = t.rows[2 * cy], t.rows[2 * cy + 1]
        spans = []
        for px in range(_W):
            ts, tn = top[px]
            bs, bn = bot[px]
            fg = _pixel_rgb(ts, t.rank(tn), flat)
            bg = _pixel_rgb(bs, t.rank(bn), flat)
            spans.append(
                Span(
                    "▀",
                    Style(
                        fg=f"#{fg[0]:02x}{fg[1]:02x}{fg[2]:02x}",
                        bg=f"#{bg[0]:02x}{bg[1]:02x}{bg[2]:02x}",
                    ),
                )
            )
        rows.append(Line(spans=tuple(spans)).to_block(min(_W, width)))
    return join_vertical(*rows)


def _grid_glyphs(view: View, width: int) -> Block:
    """Meaning by character: one sample per cell, status by glyph.

    The ramp is the same information the gradient carries, coarsened. The
    two admissions survive intact — `@` for proved, `?` for unproved — which
    is the point: a pipe loses the picture's beauty, never its claims.
    Chosen whenever hue is unavailable, and ASCII-only so it also serves the
    no-glyph case; half of a cell cannot be colored without both facets.
    """
    t = trace(view)
    rows: list[Block] = []
    for cy in range(_H):
        row = t.rows[2 * cy]  # one of the two samples; the other has no cell
        spans = []
        for status, nu in row:
            if status == INTERIOR:
                spans.append(Span(_GLYPH_INTERIOR, mark_style("membership", "interior")))
            elif status == UNRESOLVED:
                spans.append(Span(_GLYPH_UNRESOLVED, mark_style("membership", "unresolved")))
            else:
                idx = min(len(_GLYPH_RAMP) - 1, int(t.rank(nu) * len(_GLYPH_RAMP)))
                spans.append(Span(_GLYPH_RAMP[idx], mark_style("membership", "escaped")))
        rows.append(Line(spans=tuple(spans)).to_block(min(_W, width)))
    return join_vertical(*rows)


def _grid(view: View, width: int, flat: bool) -> Block:
    """Capability picks the carrier: half-blocks need both hue and non-ASCII."""
    caps = current_capabilities()
    if caps.color and caps.glyph:
        return _grid_color(view, width, flat)
    return _grid_glyphs(view, width)


# --- Rows ---


def _pct(t: Trace, status: int) -> float:
    return t.counts[status] / max(1, sum(t.counts))


def _census(view: View) -> Block:
    """One line that never overstates — and headlines the part it cannot claim.

    The unresolved share leads because it is the only figure here that is
    about the renderer rather than the set. It also has to *survive*: a
    census that spelled out all three shares overflowed 64 columns and got
    ellipsized from the right, which cut exactly the number this demo exists
    to report. The full breakdown discloses one rung up, in the legend.
    """
    t = trace(view)
    p = current_palette()
    return join_horizontal(
        Block.text("mandelbrot", p.accent.merge(Style(bold=True))),
        Block.text(
            f"  {_OPEN[2] / t.span:>6,.0f}x  budget {t.budget:>3}  ",
            Style(dim=True),
        ),
        Block.text(
            f"unresolved {_pct(t, UNRESOLVED):>3.0%}", mark_style("membership", "unresolved")
        ),
    )


def _swatches() -> tuple[str, str, str]:
    """The key's marks, in whichever channel the picture is actually using.

    A colored half-block is meaningless in a pipe — three identical glyphs —
    so the colorless key shows the glyphs the grid really drew.
    """
    caps = current_capabilities()
    if caps.color and caps.glyph:
        return ("▀", "▀", "▀")
    return (_GLYPH_RAMP[len(_GLYPH_RAMP) // 2], _GLYPH_INTERIOR, _GLYPH_UNRESOLVED)


def _legend(view: View) -> Block:
    """The declared vocabulary, rendered — each value in its own mark."""
    t = trace(view)
    swatches = _swatches()
    spans = [Span("proof ", Style(dim=True))]
    for status, name in enumerate(_STATUS_NAMES):
        style = mark_style("membership", name)
        spans.append(Span(swatches[status], style))
        spans.append(Span(f" {name} ", style if status == UNRESOLVED else Style(dim=True)))
        spans.append(Span(f"{t.counts[status]:<5} ", Style(dim=True)))
    return Line(spans=tuple(spans)).to_block(_W)


def _stats(view: View) -> Block:
    """Trace internals — what the frame spent against what it was allowed.

    The ceiling is samples x budget: the cost of a frame in which nothing
    escaped and nothing was proved. Actual spend sits far below it because
    escape is cheap and proof is free; the gap closes as the descent leaves
    the renderer more cells it cannot rule out.
    """
    t = trace(view)
    ceiling = max(1, sum(t.counts)) * t.budget
    return Block.text(
        f"span {t.span:.2e}  ·  iterations {t.iterations:,} of {ceiling:,}  ·  "
        f"{'settled' if view.settled else 'live'}",
        Style(dim=True),
    )


def _window(view: View, width: int | None, flat: bool, *extra: Block) -> Block:
    """The dressed viewing frame: field, census, and any extras.

    Inner width pins to the sample grid — every row is sized against it, so
    the border never moves no matter what the data rows do. The grid is a
    raster of the field's own domain size (_W), which is the natural inner
    width when none is offered.
    """
    w = _W if width is None else min(width - 4, _W)
    rows = [_grid(view, w, flat), truncate(_census(view), w)]
    rows += [truncate(b, w) for b in extra]
    return border(join_vertical(*rows), title="mandelbrot", chars=ROUNDED)


# --- Zoom renderers ---

# `proof` is a lens on the same trace, not a layer of detail — named at any
# depth, implied at none. `stats` is the conventional -vv facet.
_TAGS = [
    Tag("proof", "Color by what is proved, not by escape time"),
    Tag("stats", "Show trace internals (span, samples, iterations)", implied_at=3),
]


def _render(view: View, fidelity: Fidelity, width: int | None) -> Block:
    # The vocabulary travels with the render, not with the process: harnesses
    # (the liveness smoke, tools/capture.py) call `_render` directly and never
    # run `main()`, and an ambient setter at import would leak this demo's
    # declaration into every module loaded beside it.
    with use_vocabularies(MEMBERSHIP):
        depth = fidelity.depth
        flat = fidelity.shows("proof")
        extra: list[Block] = []
        if depth >= 2:
            extra.append(_legend(view))
        if fidelity.shows("stats"):
            extra.append(_stats(view))
        if depth >= 1:
            return _window(view, width, flat, *extra)
        census = _census(view)
        if width is not None:
            census = truncate(census, width)
        if not extra:
            return census
        if width is None:
            return join_vertical(census, *extra)
        return join_vertical(census, *(truncate(b, width) for b in extra))


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
        prog="mandelbrot.py",
        tags=_TAGS,
        help_args=[
            HelpArg(
                "--frame",
                "pose shown by static output (live descends from 0)",
                default=str(DEFAULT_FRAME),
            ),
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
