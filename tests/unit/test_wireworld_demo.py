"""Law tests for the wireworld pattern demo.

The demo's lesson is structured seeds: circuits authored as ASCII art,
parsed into frozen state, and the laws verify the machines actually
compute — measured clock periods, the diode's one-way verdict — by
running the shipped circuits, not by pinning frames. The three CA rules
get constructed micro-worlds of their own.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

from painted import Fidelity, Zoom
from tests.helpers import block_to_text

_DEMO = Path(__file__).resolve().parent.parent.parent / "demos" / "showcase" / "wireworld.py"


def _load():
    spec = importlib.util.spec_from_file_location("_wireworld_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_wireworld_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


ww = _load()


def _fires(circuit_name: str, lane: str, gens: int) -> list[int]:
    """Generations at which the lane's probe cell carries an electron head."""
    circuit = ww.parse(ww.CIRCUITS[circuit_name], circuit_name)
    probe = ww._PROBES[circuit_name][lane]
    hits = []
    for gen in range(gens):
        circuit = ww.step(circuit)
        if probe in set(circuit.heads):
            hits.append(gen)
    return hits


# --- Rule laws, one micro-world each ---


def test_head_becomes_tail_becomes_wire() -> None:
    line = ww.parse("~@#", "t")
    once = ww.step(line)
    assert once.tails == ((1, 0),) and (0, 0) not in once.heads
    twice = ww.step(once)
    assert (1, 0) not in twice.heads and (1, 0) not in twice.tails


def test_wire_ignites_on_one_or_two_heads_only() -> None:
    # One head ignites; three heads (the diode's whole trick) do not.
    one = ww.step(ww.parse("@#", "t"))
    assert (1, 0) in one.heads
    three = ww.step(ww.parse("@\n@#\n@", "t"))
    assert (1, 1) not in three.heads


def test_step_is_deterministic() -> None:
    a = ww._fetch("diode", 40)
    b = ww._fetch("diode", 40)
    assert a == b


# --- Circuit laws: the machines actually compute ---


def test_clocks_tick_at_their_geometric_periods() -> None:
    # Period = ring perimeter - 4: the diagonal rule cuts every corner.
    for lane, period in ww._PERIODS["clocks"].items():
        hits = _fires("clocks", lane, 120)
        assert len(hits) >= 3, f"{lane}: no pulse train reached the probe"
        gaps = {b - a for a, b in zip(hits, hits[1:])}
        assert gaps == {period}, f"{lane}: periods {gaps}, expected {period}"


def test_diode_passes_one_way_and_blocks_the_other() -> None:
    open_hits = _fires("diode", "open lane", 200)
    closed_hits = _fires("diode", "closed lane", 200)
    assert len(open_hits) >= 3, "open lane: pulses never cleared the diode"
    assert closed_hits == [], "closed lane: the diode leaked"


# --- Render laws ---


def test_render_is_pure_at_every_zoom() -> None:
    circuit = ww._fetch("diode", ww.DEFAULT_GEN)
    for zoom in Zoom:
        fid = Fidelity(depth=int(zoom))
        assert block_to_text(ww._render(circuit, fid, 80)) == block_to_text(
            ww._render(circuit, fid, 80)
        )


def test_grid_glyphs_are_the_three_states() -> None:
    text = block_to_text(ww._grid(ww._fetch("diode", ww.DEFAULT_GEN), 80))
    assert set(text) <= {"·", "@", "~", " ", "\n"}
