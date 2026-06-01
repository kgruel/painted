"""Behavioral unit test for the apps/layers.py demo.

Graduated from the old frame-text golden (tests/golden/test_demo_layers_app.py):
instead of snapshotting stripped frame text, we assert on STATE and EMISSIONS.

What is verified (each assertion grounded in source):
- AppState.volume / .counter / .layers  -- demos/apps/layers.py:40-42 (frozen dataclass fields)
- SettingsEdit.volume                    -- demos/apps/layers.py:99
- Layer.name / Layer.state               -- src/painted/tui/layer.py (frozen dataclass fields)
- LayersApp._state                       -- demos/apps/layers.py:231 (Surface app state)
- Surface._running set False by quit()    -- src/painted/tui/surface.py:196-198
- handle_key auto-emits ("ui.action", {"action": ...}) -- src/painted/tui/surface.py:184-189
  Caveat: "pop" only fires when pop_result is not None; this demo's layers Pop()
  with result=None, so commit/cancel pops surface as "stay" -- those are verified
  via STATE. The "quit" action does fire and is asserted.
- TestSurface.emissions captures emits    -- src/painted/tui/testing.py:95-104

run_to_completion() runs the WHOLE queue, so each behavior uses a fresh app
whose queue terminates exactly at the inspection point; we then read app._state.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from painted.tui.testing import TestSurface

_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_demo_layers_app_unit",
    _PROJECT / "demos" / "apps" / "layers.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

LayersApp = _mod.LayersApp


def _run(keys: list[str]) -> tuple[object, TestSurface, list]:
    """Run a fresh app to the end of `keys`; return (app, harness, frames)."""
    app = LayersApp()
    harness = TestSurface(app, width=80, height=24, input_queue=keys)
    frames = harness.run_to_completion()
    return app, harness, frames


def _ui_actions(harness: TestSurface) -> list[str]:
    """The action names auto-emitted by Surface.handle_key (surface.py:184-189)."""
    return [data["action"] for kind, data in harness.emissions if kind == "ui.action"]


def test_initial_state_is_base_layer_only() -> None:
    app, _, _ = _run([])
    assert app._state.layers[-1].name == "base"
    assert len(app._state.layers) == 1
    assert app._state.volume == 50
    assert app._state.counter == 0


def test_modal_isolation_layer_value_diverges_from_base() -> None:
    # Open settings, bump volume once. Modal-local value changes; base untouched.
    app, _, _ = _run(["s", "up"])

    # A settings layer is on top of base.
    assert len(app._state.layers) == 2
    assert app._state.layers[-1].name == "settings"

    # Modal-local SettingsEdit.volume moved 50 -> 60 (handle_settings: min(100, +10)).
    assert app._state.layers[-1].state.volume == 60

    # Base AppState.volume is unchanged -- the modal holds its own draft.
    assert app._state.volume == 50


def test_enter_commits_modal_value_and_pops_to_base() -> None:
    # NOTE: handle_settings returns Pop() with result=None, so handle_key emits
    # "stay" (it only emits "pop" when pop_result is not None -- surface.py:186).
    # The commit+pop is therefore verified via STATE, not the emission.
    app, _, _ = _run(["s", "up", "enter"])

    # Committed: base volume now reflects the modal draft (50 -> 60).
    assert app._state.volume == 60

    # Popped back to the base layer.
    assert len(app._state.layers) == 1
    assert app._state.layers[-1].name == "base"


def test_escape_cancels_without_mutating_base() -> None:
    app, _, _ = _run(["s", "up", "escape"])

    # Cancelled: base volume stays at its original value (draft discarded).
    assert app._state.volume == 50

    # Still popped back to base.
    assert len(app._state.layers) == 1
    assert app._state.layers[-1].name == "base"


def test_help_layer_push_then_pop() -> None:
    # Push help.
    pushed, _, _ = _run(["h"])
    assert len(pushed._state.layers) == 2
    assert pushed._state.layers[-1].name == "help"

    # Any key pops help back to base (handle_help returns Pop()).
    popped, _, _ = _run(["h", "x"])
    assert len(popped._state.layers) == 1
    assert popped._state.layers[-1].name == "base"


def test_q_quits() -> None:
    app, harness, _ = _run(["q"])
    assert app._running is False
    assert "quit" in _ui_actions(harness)


def test_top_layer_composites_over_base_in_overlap() -> None:
    # With settings open, the centered modal AND base chrome both render
    # (render_layers paints bottom-to-top). Structural frame fact:
    _, _, frames = _run(["s"])
    text = frames[-1].text

    # Modal marker (centered overlay) is present...
    assert "Settings" in text
    # ...and base chrome outside the modal region is still visible underneath.
    assert "Layer Demo" in text
    assert "layers: base > settings" in text
