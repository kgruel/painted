"""Behavioral unit test for the mouse.py app demo.

Graduated from the old frame-text golden (tests/golden/test_demo_mouse.py).
Instead of snapshotting stripped frame text, these tests drive mouse/key input
through TestSurface and assert on the app's STATE (canvas, color_idx, drawing,
last_pos). Frame text is only used for a single structural marker.

State fields asserted here were each confirmed by reading demos/apps/mouse.py:
  - color_idx  (int, set in __init__ and on_mouse scroll / on_key digits)
  - canvas     (dict[(x, y) -> color], mutated by _draw_at/_erase_at)
  - drawing    (bool, toggled on LEFT press/release)
  - last_pos   (tuple | None, tracked across drag, cleared on release)

Mouse input is driven the most direct way the harness supports: TestSurface
delivers MouseEvent items from input_queue straight to Surface.on_mouse
(see painted/tui/testing.py run_to_completion), so no manual handler poking is
needed. Drag MOVE events carry button=LEFT because the app's drag branch is
gated on both button==LEFT and self.drawing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from painted.tui import MouseAction, MouseButton, MouseEvent
from painted.tui.testing import TestSurface

_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_demo_mouse",
    _PROJECT / "demos" / "apps" / "mouse.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

MouseApp = _mod.MouseApp
PALETTE = _mod.PALETTE

_WIDTH = 50
_HEIGHT = 10
# Canvas area is gated by `1 <= y < height - 1`, so valid rows are 1..height-2.
_CANVAS_Y = 4


def _run(app: "MouseApp", queue: list) -> list:
    """Replay queue against app; return captured frames. Mutates app in place."""
    harness = TestSurface(app, width=_WIDTH, height=_HEIGHT, input_queue=queue)
    return harness.run_to_completion()


def test_initial_render_structural_marker() -> None:
    """The status bar header renders — single frame-text structural check."""
    app = MouseApp()
    frames = _run(app, [])
    assert "Mouse Demo" in frames[0].text
    assert app.canvas == {}
    assert app.color_idx == 0
    assert app.drawing is False


def test_scroll_advances_color_index_mod_n() -> None:
    """Scroll down advances brush index; scroll wraps mod len(PALETTE)."""
    n = len(PALETTE)

    # Scroll down once from a fresh app -> index advances by 1.
    app = MouseApp()
    _run(app, [_scroll_down()])
    assert app.color_idx == 1

    # Scroll up once from a fresh app -> (0 - 1) % n == n - 1 (wrap).
    app = MouseApp()
    _run(app, [_scroll_up()])
    assert app.color_idx == n - 1

    # Scroll down n times -> back to 0 (full wrap).
    app = MouseApp()
    _run(app, [_scroll_down() for _ in range(n)])
    assert app.color_idx == 0


def test_left_press_sets_drawing_and_places_pixel() -> None:
    """A LEFT press marks drawing state and paints a pixel with the brush color."""
    app = MouseApp()
    _run(app, [_press(MouseButton.LEFT, 5, _CANVAS_Y)])

    assert app.drawing is True
    assert app.last_pos == (5, _CANVAS_Y)
    # Pixel placed with the *current* brush color, not merely present.
    assert app.canvas[(5, _CANVAS_Y)] == PALETTE[app.color_idx]


def test_drag_draws_contiguous_pixels() -> None:
    """Press then drag draws a contiguous horizontal run via Bresenham."""
    app = MouseApp()
    queue = [
        _press(MouseButton.LEFT, 2, _CANVAS_Y),
        _move(MouseButton.LEFT, 4, _CANVAS_Y),
        _move(MouseButton.LEFT, 6, _CANVAS_Y),
        _move(MouseButton.LEFT, 8, _CANVAS_Y),
    ]
    _run(app, queue)

    # Every integer x in [2, 8] on the drag row is filled (contiguous, no gaps).
    drawn_xs = {x for (x, y) in app.canvas if y == _CANVAS_Y}
    assert drawn_xs == set(range(2, 9))
    assert app.drawing is True
    assert app.last_pos == (8, _CANVAS_Y)


def test_release_clears_drawing_state() -> None:
    """RELEASE clears drawing flag and last_pos but keeps drawn pixels."""
    app = MouseApp()
    queue = [
        _press(MouseButton.LEFT, 3, _CANVAS_Y),
        _release(MouseButton.LEFT, 3, _CANVAS_Y),
    ]
    _run(app, queue)

    assert app.drawing is False
    assert app.last_pos is None
    assert (3, _CANVAS_Y) in app.canvas  # pixel from the press survives release


def test_right_press_erases_pixel() -> None:
    """RIGHT press removes a previously drawn pixel at that position."""
    app = MouseApp()
    queue = [
        _press(MouseButton.LEFT, 7, _CANVAS_Y),
        _release(MouseButton.LEFT, 7, _CANVAS_Y),
        _press(MouseButton.RIGHT, 7, _CANVAS_Y),
    ]
    _run(app, queue)

    assert (7, _CANVAS_Y) not in app.canvas


def test_c_key_clears_canvas() -> None:
    """The 'c' key empties the canvas; a ui.key emission echoes the keypress."""
    app = MouseApp()
    queue = [
        _press(MouseButton.LEFT, 5, _CANVAS_Y),
        _release(MouseButton.LEFT, 5, _CANVAS_Y),
        "c",
    ]
    harness = TestSurface(app, width=_WIDTH, height=_HEIGHT, input_queue=queue)
    harness.run_to_completion()

    assert app.canvas == {}
    # Secondary check: harness recorded the keypress (harness echo, not app logic).
    assert ("ui.key", {"key": "c"}) in harness.emissions


# --- MouseEvent constructors (mirror the old golden's event shapes) ---


def _press(button: MouseButton, x: int, y: int) -> MouseEvent:
    return MouseEvent(action=MouseAction.PRESS, button=button, x=x, y=y)


def _release(button: MouseButton, x: int, y: int) -> MouseEvent:
    return MouseEvent(action=MouseAction.RELEASE, button=button, x=x, y=y)


def _move(button: MouseButton, x: int, y: int) -> MouseEvent:
    return MouseEvent(action=MouseAction.MOVE, button=button, x=x, y=y)


def _scroll_down() -> MouseEvent:
    return MouseEvent(action=MouseAction.SCROLL, button=MouseButton.SCROLL_DOWN, x=5, y=4)


def _scroll_up() -> MouseEvent:
    return MouseEvent(action=MouseAction.SCROLL, button=MouseButton.SCROLL_UP, x=5, y=4)
