"""Law tests for the plasma pattern demo.

Same rationale as test_life_demo.py / test_donut_demo.py: the demo's lesson
is a pure colored field of a frame counter, and liveness can't catch wrong
math. Laws over the field (bounds, motion), the two carriers (glyphs stay on
the ramp, colors stay on the gradient), and purity of the render — no pose
cosmetics are pinned.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from painted import Zoom
from tests.helpers import block_to_text, static_ctx

_DEMO = Path(__file__).resolve().parent.parent.parent / "demos" / "patterns" / "plasma.py"


def _load():
    spec = importlib.util.spec_from_file_location("_plasma_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_plasma_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


plasma = _load()


def test_field_is_normalized() -> None:
    for frame in (0, 80, 333):
        for row in plasma._sample(plasma.Plasma(frame=frame)):
            assert all(0.0 <= v <= 1.0 for v in row), f"frame {frame} leaves [0, 1]"


def test_field_actually_moves() -> None:
    a = plasma._sample(plasma.Plasma(frame=0))
    b = plasma._sample(plasma.Plasma(frame=30))
    assert a != b


def test_scene_is_a_pure_function_of_the_frame() -> None:
    for zoom in Zoom:
        ctx = static_ctx(zoom)
        pose = plasma.Plasma(frame=123)
        assert block_to_text(plasma._render(ctx, pose)) == block_to_text(plasma._render(ctx, pose))


def test_grid_glyphs_come_only_from_the_ramp() -> None:
    text = block_to_text(plasma._grid(plasma.Plasma(frame=80), 80))
    assert set(text) <= set(plasma._RAMP) | {"\n"}


def test_grid_colors_come_only_from_the_gradient() -> None:
    # Every styled cell wears a gradient style — color is computed, not ad hoc.
    block = plasma._grid(plasma.Plasma(frame=80), 80)
    gradient_fgs = {s.fg for s in plasma._STYLES}
    seen = {block.row(y)[x].style.fg for y in range(block.height) for x in range(block.width)}
    assert seen <= gradient_fgs
    # And the field actually exercises the gradient — this is a COLOR demo.
    assert len(seen) > plasma._SHADES // 2


def test_gradient_endpoints_hit_the_anchors() -> None:
    assert plasma._STYLES[0].fg == plasma._ANCHORS[0]
    assert plasma._STYLES[-1].fg == plasma._ANCHORS[-1]


def test_meter_dresses_only_observed_frames() -> None:
    # Static poses carry no timings -> no cost row; live timings -> gauge.
    ctx = static_ctx(Zoom.SUMMARY)
    assert "cost" not in block_to_text(plasma._render(ctx, plasma.Plasma(frame=80)))
    timed = plasma.Plasma(frame=80, frame_ms=(5.0, 6.0, 7.5))
    text = block_to_text(plasma._render(ctx, timed))
    assert "cost" in text and "7.5ms" in text and "33ms budget" in text


def test_runs_per_row_is_a_real_compression_measure() -> None:
    # More than one run per row (the field varies) but far fewer than one
    # per cell (smoothness compresses into spans) — the SGR-load story.
    runs = plasma._runs_per_row(plasma.Plasma(frame=80))
    assert 1.0 < runs < plasma._W / 2
