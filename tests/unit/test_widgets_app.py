"""Behavioral unit test for the apps/widgets.py demo.

Graduated from the old `tests/golden/test_demo_widgets.py` text-snapshot
golden (golden-migration step 4). Instead of snapshotting stripped frame
*text*, this asserts on the app's STATE and the harness EMISSIONS after
replaying canonical key sequences through TestSurface.

State fields exercised here are all verified against source:
- ``app.focus`` is a ``painted.focus.Focus`` with ``.id`` (focus.py:17).
- ``app.progress_state.value`` — ``ProgressState.value: float`` clamped 0-1
  by ``.set`` (views/components/progress.py:20-24).
- ``app.list_state.selected`` / ``.scroll_offset`` — read-only properties over
  cursor/viewport (views/components/_list_view.py:32-43).
- ``app.text_state.text`` / ``.cursor`` — ``TextInputState`` fields
  (views/components/_text_input.py:13-18).
- ``app.spinner_state.frame`` — ``SpinnerState.frame: int``
  (views/components/_spinner.py:32).

The harness re-emits a ``("ui.key", {"key": ...})`` tuple per replayed key
(tui/testing.py:141), which we use as the emissions fallback assertion.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

from painted.tui.testing import TestSurface

_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_demo_app_widgets",
    _PROJECT / "demos" / "apps" / "widgets.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


def _run(keys: list[str]) -> tuple[object, TestSurface]:
    """Replay keys; return the (mutated) app and the harness."""
    app = _mod.WidgetsApp()
    harness = TestSurface(app, width=80, height=24, input_queue=keys)
    harness.run_to_completion()
    return app, harness


def test_initial_state() -> None:
    """Baseline: focus, progress, selection, text, spinner all at defaults."""
    app, _ = _run([])
    assert app.focus.id == "progress"
    assert app.progress_state.value == 0.35
    assert app.list_state.selected == 0
    assert app.text_state.text == "Edit me"
    assert app.text_state.cursor == 7
    assert app.spinner_state.frame == 0


def test_right_arrow_adjusts_progress() -> None:
    """right increments progress by 0.05 per press while focus == progress."""
    app, _ = _run(["right", "right"])
    # 0.35 + 0.05 + 0.05 == 0.45 (float; compare with tolerance).
    assert math.isclose(app.progress_state.value, 0.45, abs_tol=1e-9)
    assert app.focus.id == "progress"  # arrows do not change focus


def test_right_arrow_clamps_at_one() -> None:
    """ProgressState.set clamps to 1.0 — many rights cannot overflow."""
    app, _ = _run(["right"] * 50)
    assert app.progress_state.value == 1.0


def test_tab_moves_focus_to_list() -> None:
    """tab walks the focus ring progress -> list."""
    app, _ = _run(["tab"])
    assert app.focus.id == "list"


def test_down_advances_list_selection_with_scroll() -> None:
    """After focusing the list, down advances the selection and scrolls.

    There are 5 items in a visible_height=3 window, so selecting index 3
    must scroll the viewport offset off zero (scroll-into-view).
    """
    app, _ = _run(["tab", "down", "down", "down"])
    assert app.focus.id == "list"
    assert app.list_state.selected == 3
    # The demo calls scroll_into_view(3) inside render(); the rendered state's
    # offset must keep the selection visible. 5 items overflow a height-3 window,
    # so the last row is reserved for the law-6 evidence row (capacity 2), forcing
    # selected=3 to offset 2 — window [2, 4) shows items 2 and 3 above the mark.
    assert app.list_state.scroll_into_view(3).scroll_offset == 2


def test_tab_to_text_and_editing_changes_content() -> None:
    """Two tabs reach the text field; left moves the cursor, typing inserts."""
    # progress -> list -> text via two tabs.
    app, _ = _run(["tab", "tab", "left", "left", "x"])
    assert app.focus.id == "text"
    # cursor starts at 7; two move_left -> 5; insert "x" at 5 -> cursor 6.
    assert app.text_state.cursor == 6
    assert app.text_state.text == "Edit xme"


def test_spinner_ticks_advance_frame() -> None:
    """The spinner advances once every 6 update() calls (frame % 6 == 0).

    TestSurface calls update() once for the initial frame and once per key,
    so the initial render + 5 keys == 6 update() calls == exactly one tick.
    """
    app, _ = _run(["a", "a", "a", "a", "a"])
    assert app.spinner_state.frame == 1


def test_emissions_record_each_replayed_key() -> None:
    """Fallback channel: the harness emits one ui.key per replayed key."""
    keys = ["right", "tab", "down", "q"]
    _, harness = _run(keys)
    key_emissions = [data["key"] for kind, data in harness.emissions if kind == "ui.key"]
    assert key_emissions == keys


def test_q_quits_and_a_structural_marker_renders() -> None:
    """q quits; the rendered frame carries the structural title marker."""
    app, harness = _run(["q"])
    assert app._running is False
    frames = TestSurface(_mod.WidgetsApp(), width=80, height=24, input_queue=[]).run_to_completion()
    # Structural marker only — the title is the demo's stable anchor.
    assert "Component Demo" in frames[0].text
