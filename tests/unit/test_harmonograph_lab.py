"""Behavioral tests for the interactive harmonograph instrument.

The showcase owns the curve and raster laws. These tests pin what the example
adds: immutable tuning transitions, preset/reset behavior, timer control,
modal help, responsive composition, and visible focus under a short rack.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from painted.tui import TestSurface

_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_harmonograph_lab_unit",
    _PROJECT / "demos" / "examples" / "harmonograph_lab.py",
)
lab = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = lab
_spec.loader.exec_module(lab)


def _run(
    keys: list[str], *, width: int = 100, height: int = 30
) -> tuple[object, TestSurface, list]:
    app = lab.HarmonographLab()
    harness = TestSurface(app, width=width, height=height, input_queue=keys)
    frames = harness.run_to_completion()
    return app, harness, frames


# --- Pure application transitions ---


def test_initial_tuning_reconstructs_the_showcase_score() -> None:
    state = lab.initial_state()
    assert lab.current_score(state) == lab.hm.SCORE


def test_selection_wraps_both_directions() -> None:
    state = lab.initial_state()
    assert lab.select_control(state, -1).selected == len(lab.CONTROLS) - 1
    assert lab.select_control(replace(state, selected=len(lab.CONTROLS) - 1), 1).selected == 0


def test_tuning_is_immutable_and_clamped() -> None:
    state = lab.initial_state()
    tuned = lab.tune(state, 1)
    assert tuned is not state and tuned.tuning is not state.tuning
    assert state.tuning.x_ratio == pytest.approx(1.5)
    assert tuned.tuning.x_ratio == pytest.approx(1.55)

    for _ in range(100):
        tuned = lab.tune(tuned, 1, coarse=True)
    assert tuned.tuning.x_ratio == lab.CONTROLS[0].maximum


def test_each_control_changes_the_generated_score() -> None:
    base = lab.initial_state()
    baseline = lab.current_score(base)
    for selected in range(len(lab.CONTROLS)):
        state = replace(base, selected=selected)
        assert lab.current_score(lab.tune(state, 1)) != baseline


def test_preset_and_reset_restore_the_declared_score() -> None:
    state = lab.choose_preset(lab.initial_state(), 2)
    assert state.preset == 2
    assert lab.current_score(state) == lab.PRESETS[2].score

    changed = lab.tune(state, 1)
    assert lab.current_score(changed) != lab.PRESETS[2].score
    restored = lab.reset(changed)
    assert lab.current_score(restored) == lab.PRESETS[2].score
    assert restored.frame == 0 and restored.paused is False


# --- Surface behavior ---


def test_initial_frame_is_frozen_and_shows_the_instrument() -> None:
    app, _harness, frames = _run([])
    assert app.state.frame == 0
    assert app._started is True
    assert "HARMONOGRAPH LAB" in frames[0].text
    assert "INSTRUMENT" in frames[0].text
    assert "x ratio" in frames[0].text


def test_animation_advances_then_pause_freezes_it() -> None:
    app, _harness, _frames = _run(["x", "x", "space", "x", "x"])
    assert app.state.frame == 2
    assert app.state.paused is True


def test_navigation_and_tuning_change_state() -> None:
    app, _harness, frames = _run(["down", "right", "]"])
    assert app.state.selected == 1
    assert app.state.tuning.y_ratio == pytest.approx(2 / 3 + 0.30)
    assert "y ratio" in frames[-1].text


def test_number_key_loads_preset_and_reset_rewinds_it() -> None:
    app, _harness, frames = _run(["3", "right", "r"])
    assert app.state.preset == 2
    assert app.state.frame == 0
    assert lab.current_score(app.state) == lab.PRESETS[2].score
    assert "Weave" in frames[-1].text


def test_help_is_modal_and_holds_the_animation() -> None:
    app, _harness, frames = _run(["?", "x"])
    assert app.state.help_open is True
    assert app.state.frame == 0
    assert "fine adjustment" in frames[-1].text
    assert "HARMONOGRAPH LAB" in frames[-1].text


def test_escape_closes_help_and_animation_resumes() -> None:
    app, _harness, frames = _run(["?", "escape"])
    assert app.state.help_open is False
    assert app.state.frame == 1
    assert "fine adjustment" not in frames[-1].text


def test_q_quits_from_the_base_surface() -> None:
    app, _harness, _frames = _run(["q"])
    assert app._running is False


# --- Responsive layout ---


def test_wide_layout_places_rack_beside_the_plate() -> None:
    _app, _harness, frames = _run([], width=100, height=30)
    lines = frames[-1].lines
    rack_x = next(line.index("INSTRUMENT") for line in lines if "INSTRUMENT" in line)
    assert rack_x > 60
    selected = next(line for line in lines if "x ratio" in line)
    assert "1.50" in selected


def test_narrow_layout_places_rack_below_the_plate() -> None:
    _app, _harness, frames = _run([], width=60, height=22)
    lines = frames[-1].lines
    rack_y = next(i for i, line in enumerate(lines) if "INSTRUMENT" in line)
    assert rack_y > 5
    assert "x ratio" in frames[-1].text


def test_short_rack_keeps_the_selected_control_visible() -> None:
    app, _harness, frames = _run(["down"] * 6, width=40, height=12)
    assert lab.CONTROLS[app.state.selected].id == "drift"
    assert "drift" in frames[-1].text


def test_frame_builder_honors_tiny_allocations() -> None:
    state = lab.initial_state()
    for width, height in ((0, 0), (1, 1), (2, 2), (8, 3), (20, 5), (80, 24)):
        block = lab._frame_block(state, width, height)
        assert (block.width, block.height) == (width, height)
