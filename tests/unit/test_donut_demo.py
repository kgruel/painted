"""Law tests for the donut pattern demo.

Same rationale as test_life_demo.py: the demo's lesson is a pure scene
function of a frame counter, and liveness can't catch wrong math. Laws over
the projection (bounds, shading domain, occupancy) and purity of the render —
no pose cosmetics are pinned.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from painted import Zoom
from tests.helpers import block_to_text, static_ctx

_DEMO = Path(__file__).resolve().parent.parent.parent / "demos" / "patterns" / "donut.py"


def _load():
    spec = importlib.util.spec_from_file_location("_donut_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_donut_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


donut = _load()


def test_projection_shades_within_the_ramp() -> None:
    shade = donut._project(donut.Spin(frame=60))
    indices = {idx for row in shade for idx in row}
    assert indices <= set(range(-1, 12))
    assert max(indices) >= 0, "no lit cells at all"


def test_torus_occupancy_is_sane() -> None:
    # A torus at K2=5 fills a solid band of the grid: visible but not a wall.
    for frame in (0, 60, 200):
        shade = donut._project(donut.Spin(frame=frame))
        lit = donut._lit(shade)
        total = donut._W * donut._H
        assert 0.10 < lit / total < 0.60, f"frame {frame}: coverage {lit / total:.0%}"


def test_torus_straddles_the_grid_center() -> None:
    shade = donut._project(donut.Spin(frame=60))
    xs = [x for row in shade for x, idx in enumerate(row) if idx >= 0]
    ys = [y for y, row in enumerate(shade) if any(idx >= 0 for idx in row)]
    assert min(xs) < donut._W // 2 < max(xs)
    assert min(ys) < donut._H // 2 < max(ys)


def test_scene_is_a_pure_function_of_the_frame() -> None:
    for zoom in Zoom:
        ctx = static_ctx(zoom)
        spin = donut.Spin(frame=123)
        assert block_to_text(donut._render(ctx, spin)) == block_to_text(donut._render(ctx, spin))


def test_rotation_actually_rotates() -> None:
    ctx = static_ctx(Zoom.SUMMARY)
    a = block_to_text(donut._render(ctx, donut.Spin(frame=0)))
    b = block_to_text(donut._render(ctx, donut.Spin(frame=30)))
    assert a != b


def test_meter_dresses_only_observed_frames() -> None:
    # Static poses carry no timings -> no cost row; live timings -> gauge.
    # Timings are inputs to the render, so this is deterministic.
    ctx = static_ctx(Zoom.SUMMARY)
    assert "cost" not in block_to_text(donut._render(ctx, donut.Spin(frame=60)))
    timed = donut.Spin(frame=60, frame_ms=(5.0, 6.0, 7.5))
    text = block_to_text(donut._render(ctx, timed))
    assert "cost" in text and "7.5ms" in text and "33ms budget" in text


def test_grid_glyphs_come_only_from_the_ramp() -> None:
    text = block_to_text(donut._torus(donut.Spin(frame=60), 80))
    assert set(text) <= set(donut._RAMP) | {" ", "\n"}
