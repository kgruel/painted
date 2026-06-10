"""Law tests for the fire pattern demo.

The demo's lesson is randomness carried as frozen data: a seeded LCG rides
in the state, so `step` is pure and these laws need no mocking. Laws over
propagation (bounds, fuel, cooling), reproducibility (same seed, same
inferno), and the carriers — no flame cosmetics are pinned.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from painted import Zoom
from tests.helpers import block_to_text, static_ctx

_DEMO = Path(__file__).resolve().parent.parent.parent / "demos" / "patterns" / "fire.py"


def _load():
    spec = importlib.util.spec_from_file_location("_fire_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_fire_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


fire = _load()


# --- Step laws ---


def test_step_is_pure_despite_randomness() -> None:
    # The LCG state is data, so two calls on the same Fire agree exactly.
    burning = fire._advance(fire.ignite(7), 30)
    assert fire.step(burning) == fire.step(burning)


def test_same_seed_same_inferno() -> None:
    assert fire._advance(fire.ignite(42), 50) == fire._advance(fire.ignite(42), 50)


def test_different_seeds_diverge() -> None:
    a = fire._advance(fire.ignite(1), 30)
    b = fire._advance(fire.ignite(2), 30)
    assert a.heat != b.heat


def test_heat_stays_in_range() -> None:
    burning = fire._advance(fire.ignite(7), 60)
    assert all(0 <= h < fire._LEVELS for h in burning.heat)


def test_fuel_row_never_cools() -> None:
    burning = fire._advance(fire.ignite(7), 60)
    fuel = burning.heat[(fire._H - 1) * fire._W :]
    assert all(h == fire._LEVELS - 1 for h in fuel)


def test_propagation_only_cools() -> None:
    # A cell pulls from the row below minus decay, so each new row's peak
    # can't exceed the old peak of the row it fed from.
    burning = fire._advance(fire.ignite(7), 40)
    after = fire.step(burning)
    for y in range(fire._H - 1):
        old_below = burning.heat[(y + 1) * fire._W : (y + 2) * fire._W]
        new_row = after.heat[y * fire._W : (y + 1) * fire._W]
        assert max(new_row) <= max(old_below)


def test_the_fire_actually_rises() -> None:
    # Ignition is one fuel row; a steady burn reaches well up the grid.
    assert fire._flame_height(fire.ignite(7)) == 1
    assert fire._flame_height(fire._advance(fire.ignite(7), 60)) > fire._H // 2


# --- Render laws ---


def test_render_is_pure_at_every_zoom() -> None:
    burning = fire._fetch(7, 50)
    for zoom in Zoom:
        ctx = static_ctx(zoom)
        assert block_to_text(fire._render(ctx, burning)) == block_to_text(
            fire._render(ctx, burning)
        )


def test_grid_glyphs_come_only_from_the_ramp() -> None:
    text = block_to_text(fire._grid(fire._fetch(7, 50), 80))
    assert set(text) <= set(fire._RAMP) | {"\n"}


def test_grid_colors_come_only_from_the_gradient() -> None:
    block = fire._grid(fire._fetch(7, 50), 80)
    gradient_fgs = {s.fg for s in fire._STYLES}
    seen = {block.row(y)[x].style.fg for y in range(block.height) for x in range(block.width)}
    assert seen <= gradient_fgs


def test_meter_dresses_only_observed_frames() -> None:
    from dataclasses import replace

    ctx = static_ctx(Zoom.SUMMARY)
    bare = fire._fetch(7, 50)
    assert "cost" not in block_to_text(fire._render(ctx, bare))
    timed = replace(bare, frame_ms=(5.0, 6.0, 7.5))
    text = block_to_text(fire._render(ctx, timed))
    assert "cost" in text and "7.5ms" in text and "33ms budget" in text
