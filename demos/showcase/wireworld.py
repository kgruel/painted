#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Wireworld — a cellular automaton that computes, seeded from ASCII art.

Life's seeds were a handful of coordinates; wireworld's are *circuits*.
The new concept is structured seeds: each circuit is authored as ASCII
art (`#` wire, `@` electron head, `~` tail) and parsed into the frozen
state — the art is the source code of the machine. The rules are three
lines (head becomes tail, tail becomes wire, wire ignites on exactly 1
or 2 neighboring heads); everything interesting is in the copper.

Two circuits ship. `clocks`: two ring oscillators with different
periods (their geometry IS their frequency — period = perimeter - 4,
the diagonal rule cuts every corner) driving pulse trains down parallel
wires. `diode`: twin synchronized clocks fire identical trains at two
diodes facing opposite ways — one lane passes, one lane goes dead. The
law tests run the actual circuits and assert the computation: measured
periods, pulses beyond the open diode, silence beyond the closed one.

    uv run demos/showcase/wireworld.py                    # the diode, mid-run
    uv run demos/showcase/wireworld.py --live             # watch it compute
    uv run demos/showcase/wireworld.py --circuit clocks   # two rhythms
    uv run demos/showcase/wireworld.py --gen 5 -vv        # early ticks, stats
    uv run demos/showcase/wireworld.py -q                 # one-line census
    uv run demos/showcase/wireworld.py --json             # the machine as data
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
from painted.views import sparkline

from _harness import ShowcaseArg, plate, showcase_main


# --- Data: copper and charge, frozen ---

Cells = tuple[tuple[int, int], ...]  # sorted coordinates — JSON-friendly

_HISTORY_CAP = 120  # electron-count samples kept for the sparkline


@dataclass(frozen=True)
class Circuit:
    wires: Cells  # every conductive cell (including under heads/tails)
    heads: Cells
    tails: Cells
    generation: int
    name: str
    history: tuple[int, ...]  # electron heads per generation, capped


# --- The circuit library: ASCII art is the machine's source code ---
#
# `#` wire · `@` electron head · `~` electron tail · anything else empty.
# Electrons are seeded mid-edge: a head at a ring corner would ignite both
# neighbors and split into counter-rotating twins.

# Two ring clocks, periods 14 and 10 (perimeter - 4), each driving a pulse
# train east from its mid-right cell — a mid-edge exit keeps pulses one
# head wide, which the diode geometry below depends on.
_CLOCKS_ART = """\
##~@####
#      ######################################################
########
.
.
#~@###
#    ########################################################
######
"""

# Twin period-10 clocks fire synchronized trains at two diodes facing
# opposite ways. The diode is two 2-cell blocks around an off-center gap:
# pulses entering gap-first present 3 heads to the exit cell (blocked);
# entering block-first they present 2 (passes).
_DIODE_ART = """\
#~@###                      ##
#    ######################## ############################
######                      ##
.
.
#~@###                      ##
#    ####################### #############################
######                      ##
"""

# Where the law tests (and -vv stats) listen for pulses, one probe per lane.
_PROBES: dict[str, dict[str, tuple[int, int]]] = {
    "clocks": {"slow lane": (60, 1), "fast lane": (60, 6)},
    "diode": {"open lane": (55, 1), "closed lane": (55, 6)},
}

_PERIODS: dict[str, dict[str, int]] = {  # ring perimeter - 4 corners
    "clocks": {"slow lane": 14, "fast lane": 10},
    "diode": {"open lane": 10, "closed lane": 10},
}


def parse(art: str, name: str) -> Circuit:
    """Read a circuit from its art. The drawing is the data."""
    wires, heads, tails = [], [], []
    for y, line in enumerate(art.splitlines()):
        for x, ch in enumerate(line):
            if ch in "#@~":
                wires.append((x, y))
            if ch == "@":
                heads.append((x, y))
            elif ch == "~":
                tails.append((x, y))
    circuit = Circuit(
        wires=tuple(sorted(wires)),
        heads=tuple(sorted(heads)),
        tails=tuple(sorted(tails)),
        generation=0,
        name=name,
        history=(len(heads),),
    )
    return circuit


CIRCUITS = {"clocks": _CLOCKS_ART, "diode": _DIODE_ART}
DEFAULT_CIRCUIT = "diode"
DEFAULT_GEN = 60  # static snapshot: trains underway, the diode verdict visible


# --- The step: three rules, pure function ---


def step(circuit: Circuit) -> Circuit:
    """head -> tail, tail -> wire, wire -> head iff 1 or 2 head neighbors."""
    heads = set(circuit.heads)
    charged = heads | set(circuit.tails)
    new_heads = []
    for x, y in circuit.wires:
        if (x, y) in charged:
            continue
        n = sum((x + dx, y + dy) in heads for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)
        if n in (1, 2):
            new_heads.append((x, y))
    return replace(
        circuit,
        heads=tuple(sorted(new_heads)),
        tails=tuple(sorted(heads)),
        generation=circuit.generation + 1,
        history=(*circuit.history, len(new_heads))[-_HISTORY_CAP:],
    )


def _advance(circuit: Circuit, generations: int) -> Circuit:
    for _ in range(generations):
        circuit = step(circuit)
    return circuit


# --- Fetch: snapshot and stream ---


def _fetch(circuit: str = DEFAULT_CIRCUIT, generation: int = DEFAULT_GEN) -> Circuit:
    """Static snapshot: the named circuit run to a fixed generation."""
    return _advance(parse(CIRCUITS[circuit], circuit), generation)


_FPS = 15
_MAX_GENS = 450  # ~30s of computation before the demo bows out


async def _fetch_stream(circuit: str = DEFAULT_CIRCUIT) -> AsyncIterator[Circuit]:
    """Tick at the budget; the live harness gauges its own delivery cost."""
    budget = 1.0 / _FPS
    state = parse(CIRCUITS[circuit], circuit)
    yield state
    while state.generation < _MAX_GENS:
        await asyncio.sleep(budget)
        state = step(state)
        yield state


# --- Render helpers ---


def _bounds(circuit: Circuit) -> tuple[int, int]:
    w = max(x for x, _ in circuit.wires) + 1
    h = max(y for _, y in circuit.wires) + 1
    return w, h


def _roles() -> tuple[Style, Style, Style]:
    """wire, head, tail — the classic copper/charge/cooling trio by role."""
    p = current_palette()
    return p.warning.merge(Style(dim=True)), p.accent.merge(Style(bold=True)), p.error


def _grid(circuit: Circuit, width: int) -> Block:
    wire_s, head_s, tail_s = _roles()
    heads, tails = set(circuit.heads), set(circuit.tails)
    wires = set(circuit.wires)
    w, h = _bounds(circuit)
    rows: list[Block] = []
    for y in range(h):
        spans: list[Span] = []
        for x in range(w):
            c = (x, y)
            if c in heads:
                spans.append(Span("@", head_s))
            elif c in tails:
                spans.append(Span("~", tail_s))
            elif c in wires:
                spans.append(Span("·", wire_s))
            else:
                spans.append(Span(" ", Style()))
        rows.append(Line(spans=tuple(spans)).to_block(min(w, width)))
    return join_vertical(*rows)


def _census(circuit: Circuit) -> Block:
    p = current_palette()
    return join_horizontal(
        Block.text("wireworld", p.accent.merge(Style(bold=True))),
        Block.text(
            f"  {circuit.name}  gen {circuit.generation:>3}  electrons {len(circuit.heads):>2}",
            Style(dim=True),
        ),
    )


def _legend() -> Block:
    wire_s, head_s, tail_s = _roles()
    spans = (
        Span("· wire  ", wire_s),
        Span("@ head  ", head_s),
        Span("~ tail", tail_s),
    )
    return Line(spans=spans).to_block(22)


def _electron_sparkline(circuit: Circuit, width: int) -> Block:
    # Fixed width from generation 0 — pads until history fills it, so the
    # window never widens as samples accumulate.
    spark_w = max(8, width - 16)
    return join_horizontal(
        Block.text("electrons ", Style(dim=True)),
        sparkline(list(circuit.history), spark_w, style=current_palette().accent),
        Block.text(f" {len(circuit.heads):>3}", Style(dim=True)),
    )


def _window(circuit: Circuit, width: int | None, *extra: Block) -> Block:
    """The dressed viewing frame: copper, census, and any extras.

    Inner width pins to the circuit's own bounds — every row is sized
    against it, so the border never moves no matter what the data rows do.
    When no width is offered (a pipe's natural sizing), that domain size is
    the natural inner width, not a resurrected terminal-fallback guess.
    """
    w = _bounds(circuit)[0] if width is None else min(width - 4, _bounds(circuit)[0])
    rows = [_grid(circuit, w), truncate(_census(circuit), w)]
    rows += [truncate(b, w) for b in extra]
    return plate(*rows, title="wireworld")


# --- Zoom renderers ---


def _render_minimal(circuit: Circuit, width: int | None) -> Block:
    block = _census(circuit)
    return truncate(block, width) if width is not None else block


def _render_summary(circuit: Circuit, width: int | None) -> Block:
    return _window(circuit, width)


def _render_detailed(circuit: Circuit, width: int | None) -> Block:
    w = _bounds(circuit)[0] if width is None else min(width - 4, _bounds(circuit)[0])
    return _window(circuit, width, _legend(), _electron_sparkline(circuit, w))


def _render_full(circuit: Circuit, width: int | None) -> Block:
    w = _bounds(circuit)[0] if width is None else min(width - 4, _bounds(circuit)[0])
    heads = set(circuit.heads)
    lanes = "  ·  ".join(
        f"{lane} {'.' if probe not in heads else '@'} p{_PERIODS[circuit.name][lane]}"
        for lane, probe in _PROBES[circuit.name].items()
    )
    stats = Block.text(
        f"gen {circuit.generation}  ·  copper {len(circuit.wires)}  ·  {lanes}",
        Style(dim=True),
    )
    return _window(circuit, width, _legend(), _electron_sparkline(circuit, w), stats)


def _render(circuit: Circuit, fidelity: Fidelity, width: int | None) -> Block:
    depth = fidelity.depth
    if depth >= 3:
        return _render_full(circuit, width)
    if depth >= 2:
        return _render_detailed(circuit, width)
    if depth >= 1:
        return _render_summary(circuit, width)
    return _render_minimal(circuit, width)


# --- Entry point ---


def main() -> int:
    return showcase_main(
        doc=__doc__,
        file=__file__,
        renderer=_render,
        fetch=lambda ns: _fetch(ns.circuit, ns.gen),
        fetch_stream=lambda ns: _fetch_stream(ns.circuit),
        args=(
            ShowcaseArg(
                "--circuit",
                f"machine to run: {', '.join(sorted(CIRCUITS))}",
                DEFAULT_CIRCUIT,
                choices=tuple(sorted(CIRCUITS)),
            ),
            ShowcaseArg(
                "--gen",
                "generation shown by static output (live computes from 0)",
                DEFAULT_GEN,
                type=int,
            ),
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
