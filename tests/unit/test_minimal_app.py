"""Behavioral unit test for the minimal.py app demo.

Graduated from the old text-snapshot golden (tests/golden/test_demo_minimal.py).
Instead of asserting on stripped frame text, this asserts on the app's STATE
(self.x, self.y, self.color_idx — all verified to exist in demos/apps/minimal.py)
and on the harness EMISSIONS / frame count. Frame text is used only for a single
structural marker (the status bar reflects position).

Behaviors covered:
- Movement clamps: moving right past the boundary stops; up never goes above the
  top row.
- 'c' cycles color_idx through all 6 colors and wraps back to 0.
- Quit halts processing: after 'q', a following key leaves position unchanged and
  no extra frame is captured (frame count is fixed once quit fires).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from painted.tui.testing import TestSurface

_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_demo_minimal_unit",
    _PROJECT / "demos" / "apps" / "minimal.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

MinimalApp = _mod.MinimalApp
COLORS = _mod.COLORS

WIDTH = 80
HEIGHT = 24

# Clamp boundaries derived from on_key() in minimal.py:
#   right -> min(buf.width - 10, x + 1)  => x maxes at WIDTH - 10
#   up    -> max(1, y - 1)               => y floors at 1
_X_MAX = WIDTH - 10  # 70
_Y_TOP = 1


def _run(keys: list[str]) -> tuple[MinimalApp, list]:
    app = MinimalApp()
    harness = TestSurface(app, width=WIDTH, height=HEIGHT, input_queue=keys)
    frames = harness.run_to_completion()
    return app, frames


def test_initial_state() -> None:
    """Initial state matches the demo's constructor."""
    app, frames = _run([])
    assert app.x == 5  # field verified in minimal.py __init__
    assert app.y == 3
    assert app.color_idx == 0
    # One frame: the initial render only.
    assert len(frames) == 1


def test_move_right_clamps_at_boundary() -> None:
    """Moving right past the right edge stops at WIDTH - 10 and does not overflow."""
    # Press right far more times than the available travel (5 -> 70 is 65 steps).
    app, _ = _run(["right"] * 200)
    assert app.x == _X_MAX
    # y untouched by horizontal movement.
    assert app.y == 3


def test_move_up_clamps_at_top_row() -> None:
    """Up never goes above the top row (y floors at 1)."""
    app, _ = _run(["up"] * 50)
    assert app.y == _Y_TOP
    assert app.x == 5


def test_color_cycles_through_all_and_wraps() -> None:
    """'c' advances color_idx through every color and wraps back to 0."""
    n = len(COLORS)
    assert n == 6  # demo defines 6 colors; guards the wrap arithmetic below

    # One press past each color: lands back on the starting index 0.
    app, _ = _run(["c"] * n)
    assert app.color_idx == 0

    # Partial cycle lands on the expected index.
    app, _ = _run(["c"] * 3)
    assert app.color_idx == 3 % n


def test_quit_halts_processing() -> None:
    """After 'q', a trailing key is not processed: position is unchanged and no
    extra frame is captured beyond the one produced for 'q' itself."""
    # Reuse the canonical quit sequence from the old golden.
    keys = ["right", "down", "c", "q", "left"]
    app, frames = _run(keys)

    # right: x 5 -> 6 ; down: y 3 -> 4 ; the trailing 'left' must NOT apply.
    assert app.x == 6  # would be 5 if 'left' were processed after quit
    assert app.y == 4
    assert app.color_idx == 1  # single 'c' press

    # Frames: initial + right + down + c + q = 5. The post-quit 'left' adds none.
    assert len(frames) == 5

    # Structural marker only: the final frame's status bar reflects the held
    # position, confirming the frame text tracks state.
    assert "pos=(6,4)" in frames[-1].text


def test_quit_emits_no_key_event_after_quit() -> None:
    """Emissions stop at the quit key; the trailing key produces no ui.key emit."""
    app = MinimalApp()
    harness = TestSurface(app, width=WIDTH, height=HEIGHT, input_queue=["right", "q", "left"])
    harness.run_to_completion()

    key_emits = [data["key"] for kind, data in harness.emissions if kind == "ui.key"]
    # 'left' after 'q' is never delivered, so it never emits.
    assert key_emits == ["right", "q"]
