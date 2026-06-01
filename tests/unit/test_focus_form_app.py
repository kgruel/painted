"""Behavioral unit test for the focus_form.py app demo.

Graduated from the old text-snapshot golden (`tests/golden/test_demo_focus_form.py`).
Instead of comparing stripped frame text, these tests drive the app through the
same canonical key sequences and assert on STATE: focus id/capture, per-field
text values, and the submission summary. Frame text is used only for one
structural marker.

State fields verified against `demos/apps/focus_form.py`:
- `app.focus` is a `Focus` with `.id: str` and `.captured: bool`
  (constructed line 61; `Focus` defined in `src/painted/focus.py`).
- `app.hostname` / `app.port` / `app.username` are `TextInputState` with
  `.text: str` (constructed lines 63-65; `TextInputState.text` defined in
  `src/painted/views/components/text_input.py:16`).
- `app.last_submit: str` — set by `_submit()` (lines 67, 143-148).

Emissions fallback NOT used: the app never calls `self.emit()`
(verified `grep -n emit demos/apps/focus_form.py` → no matches). The only
entries in `harness.emissions` are the synthetic `("ui.key", ...)` tuples
TestSurface appends per input — they echo the input queue, not app behavior.
So submit is asserted via `app.last_submit` (state), per the design.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from painted.tui import TestSurface

# Import the demo app without sys.path mutation (mirrors the old golden).
_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_app_focus_form",
    _PROJECT / "demos" / "apps" / "focus_form.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

FocusFormApp = _mod.FocusFormApp


def _run(keys: list[str]) -> FocusFormApp:
    """Replay keys against a fresh app; return the (mutated) app for state asserts."""
    app = FocusFormApp()
    TestSurface(app, width=60, height=18, input_queue=keys).run_to_completion()
    return app


def test_initial_state() -> None:
    app = _run([])
    assert app.focus.id == "hostname"
    assert app.focus.captured is False
    assert app.hostname.text == ""
    assert app.port.text == ""
    assert app.username.text == ""
    assert app.last_submit == ""


def test_structural_marker_present() -> None:
    # The one allowed frame-text assertion: the title is the surface's structure.
    app = FocusFormApp()
    frames = TestSurface(app, width=60, height=18, input_queue=[]).run_to_completion()
    assert "Focus Form" in frames[0].text
    assert "focus=hostname:NAV" in frames[0].text


def test_focus_ring_wraps_forward() -> None:
    # hostname -> port -> username -> submit -> hostname (4 Tabs wrap to start).
    app = _run(["tab", "tab", "tab", "tab"])
    assert app.focus.id == "hostname"
    assert app.focus.captured is False


def test_focus_ring_wraps_backward() -> None:
    # Shift-Tab once from the first field wraps to the last id (submit).
    app = _run(["shift_tab"])
    assert app.focus.id == "submit"
    assert app.focus.captured is False


def test_printable_on_nav_field_auto_captures_then_inserts() -> None:
    # A printable key while in NAV on a text field captures, then inserts.
    app = _run(["d"])
    assert app.focus.id == "hostname"
    assert app.focus.captured is True
    assert app.hostname.text == "d"


def test_escape_releases_capture() -> None:
    # Capture hostname via a printable, then Esc releases (no submit on hostname).
    app = _run(["h", "escape"])
    assert app.focus.id == "hostname"
    assert app.focus.captured is False
    assert app.hostname.text == "h"


def test_enter_releases_capture_on_non_submit_field() -> None:
    # On port, Enter while captured is release-only (no submit side effect).
    app = _run(["tab", "9", "enter"])
    assert app.focus.id == "port"
    assert app.focus.captured is False
    assert app.port.text == "9"
    assert app.last_submit == ""


def test_typing_scenario_field_values_and_focus() -> None:
    # Old golden's "typing" sequence: type into hostname, Tab, type into port.
    app = _run(list("db") + ["tab"] + list("5432"))
    assert app.hostname.text == "db"
    assert app.port.text == "5432"
    assert app.focus.id == "port"
    assert app.focus.captured is True


def test_submit_collects_field_values() -> None:
    # Old golden's "submit" sequence: fill all three fields, Tab to submit, Enter.
    keys = list("db") + ["tab"] + list("5432") + ["tab"] + list("sam") + ["tab", "enter"]
    app = _run(keys)
    assert app.hostname.text == "db"
    assert app.port.text == "5432"
    assert app.username.text == "sam"
    assert app.focus.id == "submit"
    assert app.last_submit == "Submitted: hostname=db  port=5432  username=sam"
