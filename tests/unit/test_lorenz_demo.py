"""Law tests for the lorenz pattern demo.

The demo's lessons are temporal accumulation (trails as frozen data) and
sensitive dependence (the twin tracers). Both are exactly law-shaped: a
fixed integrator makes divergence deterministic, and the trail is plain
data with a cap. No butterfly cosmetics are pinned.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import replace
from pathlib import Path

from painted import Zoom
from tests.helpers import block_to_text, static_ctx

_DEMO = Path(__file__).resolve().parent.parent.parent / "demos" / "showcase" / "lorenz.py"


def _load():
    spec = importlib.util.spec_from_file_location("_lorenz_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_lorenz_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


lorenz = _load()


# --- Flight laws ---


def test_integration_is_deterministic() -> None:
    assert lorenz._advance(lorenz.seed_orbit(), 100) == lorenz._advance(lorenz.seed_orbit(), 100)


def test_the_orbit_stays_on_the_attractor() -> None:
    # Lorenz trajectories are bounded; a long flight never leaves the box.
    orbit = lorenz.seed_orbit()
    for _ in range(600):
        orbit = lorenz.step(orbit)
        for tr in orbit.tracers:
            x, y, z = tr.pos
            assert abs(x) < 30 and abs(y) < 35 and -1 < z < 60


def test_steps_are_continuous() -> None:
    # The integrator's frame-to-frame motion is small — no teleporting,
    # which is also what makes the trail read as a curve.
    orbit = lorenz._advance(lorenz.seed_orbit(), 50)
    after = lorenz.step(orbit)
    for before, now in zip(orbit.tracers, after.tracers):
        assert math.dist(before.pos, now.pos) < 3.0


def test_trail_accumulates_then_caps() -> None:
    young = lorenz._advance(lorenz.seed_orbit(), 10)
    assert len(young.tracers[0].trail) == 11  # seed point + 10 steps
    old = lorenz._advance(lorenz.seed_orbit(), lorenz._TRAIL_CAP + 50)
    assert len(old.tracers[0].trail) == lorenz._TRAIL_CAP
    assert old.tracers[0].trail[-1] == old.tracers[0].pos


def test_twin_tracers_diverge() -> None:
    # Sensitive dependence, deterministically: starts under a cell apart
    # end up macroscopically separated within the demo's own flight time.
    assert lorenz.seed_orbit().history[0] < 0.1
    orbit = lorenz._advance(lorenz.seed_orbit(), lorenz.DEFAULT_FRAME)
    assert orbit.history[-1] > 5.0


# --- Render laws ---


def test_render_is_pure_at_every_zoom() -> None:
    orbit = lorenz._fetch(200)
    for zoom in Zoom:
        ctx = static_ctx(zoom)
        assert block_to_text(lorenz._render(ctx, orbit)) == block_to_text(
            lorenz._render(ctx, orbit)
        )


def test_grid_glyphs_come_only_from_the_age_ramp() -> None:
    text = block_to_text(lorenz._grid(lorenz._fetch(200), 80))
    assert set(text) <= set(lorenz._AGE_GLYPHS) | {" ", "\n"}


def test_young_points_outrank_old_in_a_shared_cell() -> None:
    # Temporal accumulation law: where trail crosses itself, the render
    # shows the youngest age class.
    orbit = lorenz._fetch(lorenz._TRAIL_CAP + 100)  # trail full, crossings certain
    text = block_to_text(lorenz._grid(orbit, 80))
    assert "@" in text  # the head's age class survives every collision
