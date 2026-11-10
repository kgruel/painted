#!/usr/bin/env python3
"""Sandpile — a heap that forgets the order it was built in.

The abelian sandpile: a cell holding four grains topples, giving one to each
neighbour; grains pushed past the edge are gone. Three sites are fed a grain
each per frame. Topple in any order and the same pile results — so the still
(one bulk settle) and the animation (one frame at a time) are the same data,
by theorem rather than by care. Half-block cells carry two samples; without
color, four ASCII marks carry the four stable heights.

    painted demos sandpile --live          # thirty seconds of avalanches
    painted demos sandpile --frame 2000    # a later, fuller table
    painted demos sandpile -v              # legend + avalanche history
    painted demos sandpile --stats         # the grain ledger
    painted demos sandpile --note          # maker's note
    painted demos sandpile --json          # the pile as data

    uv run demos/showcase/sandpile.py --live
    uv run demos/showcase/sandpile.py --frame 2000
    uv run demos/showcase/sandpile.py -v
    uv run demos/showcase/sandpile.py --stats
    uv run demos/showcase/sandpile.py --note
    uv run demos/showcase/sandpile.py --json
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

from painted import Block, Fidelity, Line, Span, Style, Wrap, fit_to_width, join_horizontal
from painted import join_vertical
from painted.capabilities import current_capabilities
from painted.cli import Tag
from painted.palette import current_palette
from painted.views import sparkline

from _harness import ShowcaseArg, plate, showcase_main
from _plaque import NOTE_TAG, Plaque, render_plaque

# --- Data: a frozen table ---

_COLS, _ROWS = 73, 36  # samples; odd width puts a site on the mirror axis
SITES = ((18, 18), (36, 18), (54, 18))  # mirror-symmetric about column 36
_HISTORY = 64  # avalanche sizes kept for the sparkline
DEFAULT_FRAME = 900

Heights = tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class Pile:
    frame: int  # one grain per site per frame
    heights: Heights  # rows of stable heights, each 0..3
    spilled: int  # grains pushed off the table, ever
    toppled: int  # topplings, ever (the odometer — also order-independent)
    recent: tuple[int, ...] = ()  # topplings caused by each of the last frames

    @property
    def dropped(self) -> int:
        return self.frame * len(SITES)

    @property
    def resting(self) -> int:
        return sum(map(sum, self.heights))


# --- The rule ---


def _feed(pile: Pile, grains: int) -> tuple[Heights, int, int]:
    """Add ``grains`` to every site and topple to rest: (heights, toppled, spilled).

    A cell at ``h >= 4`` topples ``h // 4`` times at once. Batching is legal
    for the same reason everything else here is: the order does not matter.
    """
    grid = [list(row) for row in pile.heights]
    for x, y in SITES:
        grid[y][x] += grains
    toppled = spilled = 0
    stack = list(SITES)
    while stack:
        x, y = stack.pop()
        times, grid[y][x] = divmod(grid[y][x], 4)
        if not times:
            continue
        toppled += times
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < _COLS and 0 <= ny < _ROWS:
                grid[ny][nx] += times
                if grid[ny][nx] >= 4:
                    stack.append((nx, ny))
            else:
                spilled += times
    return tuple(map(tuple, grid)), toppled, spilled


def settle(frame: int) -> Pile:
    """The pile at ``frame``, in one bulk settle — no history, no intermediate piles."""
    empty = Pile(0, ((0,) * _COLS,) * _ROWS, 0, 0)
    heights, toppled, spilled = _feed(empty, frame)
    return Pile(frame, heights, spilled, toppled)


def step(pile: Pile) -> Pile:
    """One frame: a grain on each site, toppled to rest. Pure."""
    heights, toppled, spilled = _feed(pile, 1)
    return Pile(
        frame=pile.frame + 1,
        heights=heights,
        spilled=pile.spilled + spilled,
        toppled=pile.toppled + toppled,
        recent=(*pile.recent, toppled)[-_HISTORY:],
    )


# --- Fetch: snapshot and stream ---


def _fetch(frame: int = DEFAULT_FRAME) -> Pile:
    """Bulk-settle to just before ``frame``, then step — so the avalanche
    history is the one the animation would have carried here."""
    pile = settle(max(0, frame - _HISTORY))
    while pile.frame < frame:
        pile = step(pile)
    return pile


_FPS = 24
_STEPS_PER_TICK = 4  # feeding outruns the frame rate: the table fills in thirty seconds


async def _fetch_stream(start: int = 0) -> AsyncIterator[Pile]:
    pile = _fetch(start)
    for _ in range(30 * _FPS):
        yield pile
        await asyncio.sleep(1 / _FPS)
        for _ in range(_STEPS_PER_TICK):
            pile = step(pile)


# --- Carriers ---

# Height is the whole vocabulary: four stable values, four inks, four marks.
_INK = ("#0a1020", "#2f5d8a", "#c9772e", "#f6e7b4")
_MARK = " .o#"


def _picture(heights: Heights) -> Block:
    caps = current_capabilities()
    rows = []
    for top, bottom in zip(heights[::2], heights[1::2]):
        spans = []
        for a, b in zip(top, bottom):
            if caps.color and caps.glyph:
                spans.append(Span("▀", Style(fg=_INK[a], bg=_INK[b])))
            else:
                # One mark for two samples: the taller, so a lone grain survives.
                h = max(a, b)
                spans.append(Span(_MARK[h], Style(fg=_INK[h]) if caps.color and h else Style()))
        rows.append(Line(spans=tuple(spans)).to_block(len(top)))
    return join_vertical(*rows)


def _crop(heights: Heights, columns: int) -> Heights:
    """The centre ``columns`` of the table. A cellular automaton cannot be
    resampled — a smaller table is a different pile — so narrow delivery
    windows the real one, and ``_render`` says so."""
    x0 = (_COLS - columns) // 2
    return tuple(row[x0 : x0 + columns] for row in heights)


PLAQUE = Plaque(
    title="What the pile forgets",
    note=(
        "The rule is one sentence: four grains is too many, so give one to each "
        "neighbour. What falls out of it is a theorem. Drop the grains in any order, "
        "topple in any order, and you arrive at the same pile. It keeps the count "
        "and forgets the sequence.",
        "I picked it because that is the property this renderer asks of everything "
        "else. A still frame is computed in one bulk settle; the animation gets there "
        "a grain at a time; a test holds the two equal cell for cell. Nobody "
        "synchronised them. When the state is a value and the picture is a function "
        "of it, how you got here stops being something the picture can disagree about.",
        "The avalanches are the part I can't predict. Same rule, same three sites, and "
        "one grain moves nothing while the next moves four hundred cells.",
    ),
    maker="Fable",
)

_TAGS = [NOTE_TAG, Tag("stats", "Show the grain ledger", implied_at=3)]


def _render(pile: Pile, fidelity: Fidelity, width: int | None) -> Block:
    outer = _COLS + 2 if width is None else max(0, width)
    p = current_palette()
    caps = current_capabilities()

    def text(value: str) -> Block:
        return Block.text(value, p.muted, width=outer, wrap=Wrap.ELLIPSIS)

    last = pile.recent[-1] if pile.recent else 0
    if fidelity.depth <= 0 or outer < 6:
        parts = [text(f"sandpile / frame {pile.frame} / {pile.dropped} grains / last slide {last}")]
    else:
        columns = min(_COLS, outer - 2)
        picture = _picture(_crop(pile.heights, columns))
        parts = [fit_to_width(plate(picture, title="sandpile"), outer)]
        if columns < _COLS:
            parts.append(text(f"centre {columns} of {_COLS} columns shown"))

    if fidelity.depth >= 2:
        if caps.color and caps.glyph:
            swatches = [Block.text("height ", p.muted)]
            for h, ink in enumerate(_INK):
                swatches += [Block.text("██", Style(fg=ink)), Block.text(f" {h}  ", p.muted)]
            parts.append(fit_to_width(join_horizontal(*swatches), outer))
        else:
            parts.append(text("height  " + "  ".join(f"'{m}' {h}" for h, m in enumerate(_MARK))))
        label = Block.text("slides ", p.muted)
        tail = Block.text(f" {last:>5}", p.muted)
        spark = sparkline(
            list(pile.recent), max(1, min(_HISTORY, outer - label.width - tail.width)),
            style=p.accent,
        )
        parts.append(fit_to_width(join_horizontal(label, spark, tail), outer))
    if fidelity.depth >= 3 or fidelity.shows("stats"):
        # The ledger balances or the rule is broken: nothing is created, only spilled.
        parts.append(
            text(
                f"dropped {pile.dropped} = resting {pile.resting} + spilled {pile.spilled}"
                f" / topplings {pile.toppled}"
            )
        )
    note = render_plaque(PLAQUE, fidelity=fidelity, width=outer)
    if note is not None:
        parts.append(note)
    return fit_to_width(join_vertical(*parts, gap=1), outer)


def main() -> int:
    return showcase_main(
        doc=__doc__,
        file=__file__,
        renderer=_render,
        fetch=lambda ns: _fetch(ns.frame),
        # An unasked-for --frame means "the default still"; live then grows from empty.
        fetch_stream=lambda ns: _fetch_stream(0 if ns.frame == DEFAULT_FRAME else ns.frame),
        args=(
            ShowcaseArg("--frame", "frame shown by a still (live grows from empty)", DEFAULT_FRAME, type=int),
        ),
        tags=_TAGS,
    )


if __name__ == "__main__":
    sys.exit(main())
