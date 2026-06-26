"""Law tests for the Life pattern demo.

Demos are documentation and the liveness smoke only proves they render — but
life.py's lesson is that a pure step function animates through the harness,
and a *wrong* Life is a broken lesson liveness can't catch. These are law
tests against the demo's pure core (oscillator periods, still lifes, glider
translation, determinism), not snapshots: no cosmetics are pinned.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

from painted import Zoom
from tests.helpers import block_to_text, static_ctx

_DEMO = Path(__file__).resolve().parent.parent.parent / "demos" / "showcase" / "life.py"


def _load():
    spec = importlib.util.spec_from_file_location("_life_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_life_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


life = _load()


def _world(cells: tuple[tuple[int, int], ...]):
    """A LifeWorld with explicit cells, far from the torus seam."""
    base = life.seed_world()
    return replace(base, cells=tuple(sorted(cells)))


# --- Step laws ---


def test_empty_world_stays_empty() -> None:
    world = _world(())
    assert life.step(world).cells == ()


def test_block_is_a_still_life() -> None:
    block = ((10, 10), (11, 10), (10, 11), (11, 11))
    world = _world(block)
    assert life.step(world).cells == tuple(sorted(block))


def test_blinker_oscillates_with_period_two() -> None:
    blinker = ((10, 10), (11, 10), (12, 10))
    world = _world(blinker)
    once = life.step(world)
    assert once.cells != world.cells
    assert life.step(once).cells == world.cells


def test_glider_translates_by_one_diagonal_every_four_steps() -> None:
    world = _world(tuple((x + 10, y + 10) for x, y in life.SEEDS["glider"]))
    moved = world
    for _ in range(4):
        moved = life.step(moved)
    expected = tuple(sorted(((x + 1) % world.cols, (y + 1) % world.rows) for x, y in world.cells))
    assert moved.cells == expected


def test_step_wraps_on_the_torus() -> None:
    # A blinker straddling the right edge must wrap, not be clipped.
    cols = life.seed_world().cols
    blinker = ((cols - 1, 10), (0, 10), (1, 10))
    world = _world(blinker)
    once = life.step(world)
    assert once.cells == tuple(sorted(((0, 9), (0, 10), (0, 11))))


def test_step_is_deterministic_and_tracks_generation() -> None:
    world = life.seed_world("acorn")
    a, b = life.step(world), life.step(world)
    assert a == b
    assert a.generation == world.generation + 1
    assert a.history[-1] == len(a.cells)


# --- Fetch + render laws ---


def test_fetch_is_deterministic() -> None:
    assert life._fetch("r-pentomino", 50) == life._fetch("r-pentomino", 50)


def test_render_is_pure_at_every_zoom() -> None:
    world = life._fetch("glider", 8)
    for zoom in Zoom:
        ctx = static_ctx(zoom)
        assert block_to_text(life._render(ctx, world)) == block_to_text(life._render(ctx, world))


def test_grid_pairs_rows_into_half_blocks() -> None:
    # One cell in an even row and one directly below it merge into one █.
    world = _world(((10, 10), (10, 11)))
    text = block_to_text(life._grid(world, 80))
    row = text.splitlines()[5]  # terminal row 5 holds grid rows 10 and 11
    assert row[10] == "█"
