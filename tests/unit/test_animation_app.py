"""Behavioral unit test for the apps/animation.py demo.

Graduated from the demo-golden `tests/golden/test_demo_animation.py`, which
snapshotted stripped frame text. This version asserts on STATE and EMISSIONS
instead: the timer-driven render loop (`update()` cadence + `mark_dirty()`),
the first-frame freeze, spinner/progress/counter advancement, and the
pause/resume/reset controls.

State fields asserted are all confirmed to exist in demos/apps/animation.py:
  - app.frame          (int, set in __init__, advanced in update)
  - app.counter        (int, set in __init__, advanced in update)
  - app.paused         (bool, toggled in on_key "space")
  - app._started       (the "started latch", reset by on_key "r")
  - app.spinner_state  (SpinnerState; .frame is its tick counter)
  - app.progress_state (ProgressState; .value is the 0..1 fill)

The "x" key is intentionally an unhandled key: it is a no-op in on_key but
TestSurface still runs update() after every input, so it drives one tick per
press. The canonical key sequences are reused from the old golden test.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from painted.tui import TestSurface

_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_app_animation",
    _PROJECT / "demos" / "apps" / "animation.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

AnimationApp = _mod.AnimationApp


def _run(keys: list[str]) -> tuple[AnimationApp, TestSurface, list]:
    app = AnimationApp()
    harness = TestSurface(app, width=60, height=12, input_queue=keys)
    frames = harness.run_to_completion()
    return app, harness, frames


def test_initial_frame_is_frozen() -> None:
    """The first update() arms the started latch and returns without advancing.

    So after the initial frame (no input) all animation state is still at zero.
    """
    app, _harness, frames = _run([])

    assert app._started is True  # latch armed by the first update()
    assert app.frame == 0
    assert app.counter == 0
    assert app.spinner_state.frame == 0
    assert app.progress_state.value == 0.0

    # Structural marker: the status line reflects the frozen frame and RUNNING.
    assert "frame=0000" in frames[0].lines[0]
    assert "RUNNING" in frames[0].lines[0]


def test_ticks_advance_state() -> None:
    """Each post-latch tick advances frame, spinner, progress, and counter."""
    app, _harness, _frames = _run(["x"] * 6)

    assert app.frame == 6
    assert app.counter == 6
    assert app.spinner_state.frame == 6  # tick() called once per advancing update
    # progress steps by 0.03 each tick; 6 * 0.03 ≈ 0.18 (float accumulation).
    assert app.progress_state.value == pytest.approx(0.18)
    assert app.progress_state.value > 0.0


def test_space_pauses_and_freezes_state() -> None:
    """'space' toggles paused; while paused, update() is a no-op."""
    keys = ["x"] * 3 + ["space"] + ["x"] * 3
    app, _harness, _frames = _run(keys)

    assert app.paused is True
    # 3 ticks advanced before the pause, the 3 after are frozen.
    assert app.frame == 3
    assert app.counter == 3
    assert app.spinner_state.frame == 3


def test_space_resumes() -> None:
    """A second 'space' un-pauses and ticks resume advancing."""
    keys = ["x"] * 3 + ["space"] + ["x"] * 3 + ["space"] + ["x"] * 2
    app, _harness, frames = _run(keys)

    assert app.paused is False
    # 3 before pause + 0 while paused + 2 after resume = 5... but the resume
    # press itself runs an advancing update too, so 3 + 3 = 6.
    assert app.frame == 6
    assert "RUNNING" in frames[-1].lines[0]


def test_reset_clears_state_and_rearms_latch() -> None:
    """'r' zeroes frame/counter/progress/spinner and re-arms the started latch."""
    app, _harness, _frames = _run(["x"] * 4 + ["r"])

    assert app.frame == 0
    assert app.counter == 0
    assert app.progress_state.value == 0.0
    assert app.spinner_state.frame == 0
    assert app.paused is False
    # The update() following the 'r' press re-arms (and consumes) the latch.
    assert app._started is True


def test_reset_then_ticks_advance_from_zero() -> None:
    """After reset, subsequent ticks advance from a clean zero baseline."""
    app, _harness, _frames = _run(["x"] * 4 + ["r"] + ["x"] * 2)

    assert app.frame == 2
    assert app.counter == 2
    assert app.spinner_state.frame == 2


def test_progress_wraps_at_full() -> None:
    """Progress wraps back to 0.0 once a step would reach or exceed 1.0."""
    # 33 ticks -> ~0.99; the 34th step (~0.99 + 0.03 >= 1.0) wraps to 0.0.
    app33, _h33, _f33 = _run(["x"] * 33)
    assert app33.progress_state.value == pytest.approx(0.99)  # not yet wrapped
    assert app33.progress_state.value < 1.0

    app34, _h34, _f34 = _run(["x"] * 34)
    assert app34.frame == 34
    assert app34.progress_state.value == 0.0  # wrapped


def test_emissions_record_each_key() -> None:
    """TestSurface emits a ui.key observation per input, in order."""
    _app, harness, _frames = _run(["x", "space", "r"])

    assert harness.emissions == [
        ("ui.key", {"key": "x"}),
        ("ui.key", {"key": "space"}),
        ("ui.key", {"key": "r"}),
    ]
