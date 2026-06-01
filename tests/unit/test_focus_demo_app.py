"""Behavioral unit test for the focus.py pattern demo's FocusDemoApp.

Graduated from the old `tests/golden/test_demo_focus.py`, which snapshotted
stripped frame TEXT at each zoom level. That guarded *how the result is drawn*,
not *what the app does*. This test asserts the demo's actual behavior: for each
scenario it drives FocusDemoApp through TestSurface and checks the per-scenario
domain EMISSIONS — capture-vs-nav routing, focus-ring wrap, cursor movement
under capture, and command-run only when a widget is captured.

The demo defines the scenarios (`SCENARIOS`) with their own
`expected_emissions` / `unexpected_emissions`, and a `run_scenario` runner that
drives `FocusDemoApp` via `TestSurface` and returns captured emissions. We drive
that runner and re-derive the assertions here from the raw emissions (ignoring
the low-level `ui.key` channel that TestSurface adds for every key) so the test
checks the app, not the demo's own pass/fail bookkeeping.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Import the demo by file path — no sys.path mutation (mirrors the golden tests).
# Must register in sys.modules so the module's dataclasses resolve their module.
_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_demo_focus_app",
    _PROJECT / "demos" / "patterns" / "focus.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

SCENARIOS = _mod.SCENARIOS
run_scenario = _mod.run_scenario
FocusDemoApp = _mod.FocusDemoApp

# The harness adds this synthetic emission for every key; it is not a domain
# signal, so per-scenario expectation checks ignore it.
_UI_KEY = "ui.key"


def _emission_kinds(result) -> set[str]:
    """Domain emission kinds observed in a scenario run (ui.key excluded)."""
    return {kind for kind, _ in result.emissions if kind != _UI_KEY}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scenario_expected_emissions_present(scenario):
    result = run_scenario(scenario)
    kinds = _emission_kinds(result)
    for expected in scenario.expected_emissions:
        assert expected in kinds, (
            f"scenario {scenario.name!r}: expected emission {expected!r} not seen; "
            f"saw {sorted(kinds)}"
        )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scenario_unexpected_emissions_absent(scenario):
    result = run_scenario(scenario)
    kinds = _emission_kinds(result)
    for forbidden in scenario.unexpected_emissions:
        assert forbidden not in kinds, (
            f"scenario {scenario.name!r}: forbidden emission {forbidden!r} was emitted; "
            f"saw {sorted(kinds)}"
        )


def test_capture_required_no_command_without_capture():
    """A cursor key in NAV mode is ignored (key.ignored), not routed; entering a
    widget captures it; escape releases it. No command runs in this scenario."""
    scenario = next(s for s in SCENARIOS if s.name == "capture required")
    result = run_scenario(scenario)
    kinds = _emission_kinds(result)
    # NAV-mode key was ignored, capture took over, cursor moved, then released.
    assert "key.ignored" in kinds
    assert "focus.capture" in kinds
    assert "services.cursor" in kinds
    assert "focus.release" in kinds
    # Command run never happens here — no search widget was captured/entered.
    assert "cmd.run" not in kinds


def test_ring_navigation_wraps_without_capture():
    """Tab/Shift+Tab move focus around the ring without ever capturing."""
    scenario = next(s for s in SCENARIOS if s.name == "ring navigation")
    result = run_scenario(scenario)
    moves = [data for kind, data in result.emissions if kind == "focus.move"]
    assert moves, "expected at least one focus.move"
    # Three nav keys (tab, tab, shift_tab) -> three moves around services/search/details.
    assert len(moves) == 3
    assert [m["to_id"] for m in moves] == ["search", "details", "search"]
    assert all(m["to_id"] in _mod.WIDGETS for m in moves)
    assert "focus.capture" not in _emission_kinds(result)


def test_cursor_moves_only_under_capture():
    """services.cursor carries the new index; movement happens only after capture."""
    scenario = next(s for s in SCENARIOS if s.name == "capture required")
    result = run_scenario(scenario)
    cursor_events = [data for kind, data in result.emissions if kind == "services.cursor"]
    assert cursor_events, "expected a services.cursor emission under capture"
    # keys: j(ignored, nav) -> enter(capture) -> j(cursor 0->1) -> escape -> q
    assert cursor_events[0]["index"] == 1
    assert cursor_events[0]["service"] == _mod.SERVICES[1].name


def test_command_runs_only_when_captured():
    """fuzzy search: focus -> capture -> type query -> select -> enter runs a command."""
    scenario = next(s for s in SCENARIOS if s.name == "fuzzy search")
    result = run_scenario(scenario)
    kinds = _emission_kinds(result)
    assert "search.query" in kinds
    assert "search.select" in kinds
    runs = [data for kind, data in result.emissions if kind == "cmd.run"]
    assert len(runs) == 1, "exactly one command should run"
    # Typed "dp" then selected next match, then enter -> a non-empty deploy command.
    assert runs[0]["command"]
    assert runs[0]["query"] == "dp"
    assert runs[0]["command"] in _mod.COMMANDS


def test_app_quits_on_q():
    """The app stops running once 'q' is processed (TestSurface honors quit)."""
    app = FocusDemoApp()
    harness = _mod.TestSurface(app, width=88, height=22, input_queue=["q"], capture_writes=False)
    harness.run_to_completion()
    assert app._running is False
    assert ("ui.quit", {"focus": "services", "captured": False}) in harness.emissions
