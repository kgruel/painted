"""Law tests for the boids pattern demo.

The demo's lesson is continuous agents projected onto cells, with flocking
emerging from three local rules. Each rule is pinned with a constructed
case (deterministic, no mocking — randomness is frozen data), plus the
conservation and clamp laws that keep the world sane. No flight cosmetics
are pinned.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import replace
from pathlib import Path

from painted import Fidelity, Zoom
from tests.helpers import block_to_text

_DEMO = Path(__file__).resolve().parent.parent.parent / "demos" / "showcase" / "boids.py"


def _load():
    spec = importlib.util.spec_from_file_location("_boids_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_boids_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


boids = _load()


def _flock(members: tuple[tuple[float, float, float, float], ...]):
    """A Flock with explicit members, away from the torus seam."""
    base = boids.seed_flock()
    return replace(base, boids=members, history=(boids._spread(members),))


# --- World laws ---


def test_same_seed_same_flight() -> None:
    assert boids._advance(boids.seed_flock(42), 40) == boids._advance(boids.seed_flock(42), 40)


def test_different_seeds_diverge() -> None:
    a = boids._advance(boids.seed_flock(1), 20)
    b = boids._advance(boids.seed_flock(2), 20)
    assert a.boids != b.boids


def test_flock_size_is_conserved() -> None:
    flown = boids._advance(boids.seed_flock(7), 60)
    assert len(flown.boids) == boids._N


def test_positions_stay_on_the_torus() -> None:
    flown = boids._advance(boids.seed_flock(7), 60)
    assert all(0 <= x < boids._W and 0 <= y < boids._GH for x, y, _, _ in flown.boids)


def test_speeds_respect_the_clamp() -> None:
    flown = boids._advance(boids.seed_flock(7), 60)
    for _, _, vx, vy in flown.boids:
        speed = math.hypot(vx, vy)
        assert boids._V_MIN - 1e-9 <= speed <= boids._V_MAX + 1e-9


# --- Rule laws, one constructed case each ---


def test_a_loner_flies_straight() -> None:
    # No neighbors -> no forces: heading unchanged, position advanced.
    lone = _flock(((20.0, 20.0, 0.5, 0.0),))
    after = boids.step(lone)
    x, y, vx, vy = after.boids[0]
    assert (vx, vy) == (0.5, 0.0)
    assert (x, y) == (20.5, 20.0)


def test_separation_repels_a_crowded_pair() -> None:
    # Two boids inside personal space, flying parallel: they move apart.
    a = (20.0, 20.0, 0.5, 0.0)
    b = (20.0, 21.5, 0.5, 0.0)
    after = boids.step(_flock((a, b)))
    gap = abs(boids._delta(after.boids[0][1], after.boids[1][1], boids._GH))
    assert gap > 1.5


def test_alignment_turns_a_boid_with_traffic() -> None:
    # A boid crossing a stream of +x flyers (outside personal space, inside
    # sight) gains +x velocity.
    crosser = (30.0, 22.0, 0.0, 0.5)
    stream = tuple(
        (30.0 + dx, 22.0 + dy, 1.0, 0.0) for dx, dy in ((-5, -4), (5, -4), (-5, 4), (5, 4))
    )
    after = boids.step(_flock((crosser, *stream)))
    assert after.boids[0][2] > 0.0


def test_cohesion_pulls_toward_the_cluster() -> None:
    # A boid with a cluster to its left (visible, not crowding) tilts left.
    drifter = (36.0, 22.0, 0.0, 0.5)
    cluster = tuple((28.0, 22.0 + dy, 0.0, 0.5) for dy in (-1.5, 0.0, 1.5))
    after = boids.step(_flock((drifter, *cluster)))
    assert after.boids[0][2] < 0.0


def test_spread_falls_as_flocks_form() -> None:
    # Emergence as data: a flown flock is tighter than its random scatter.
    start = boids.seed_flock(7)
    flown = boids._advance(start, 300)
    assert flown.history[-1] < start.history[0]


# --- Render laws ---


def test_render_is_pure_at_every_zoom() -> None:
    flock = boids._fetch(7, 50)
    for zoom in Zoom:
        fid = Fidelity(depth=int(zoom))
        assert block_to_text(boids._render(flock, fid, 80)) == block_to_text(
            boids._render(flock, fid, 80)
        )


def test_grid_pairs_rows_into_half_blocks() -> None:
    # One boid in an even pixel row and one directly below it merge into one █.
    pair = _flock(((10.2, 10.4, 0.5, 0.0), (10.7, 11.6, 0.5, 0.0)))
    text = block_to_text(boids._grid(pair, 80))
    assert text.splitlines()[5][10] == "█"
