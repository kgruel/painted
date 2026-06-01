"""Behavioral unit test for the apps/search_filter.py demo.

Graduated from the demo-golden `test_demo_search_filter.py` (golden-migration
step 4). The old golden snapshotted stripped frame *text*; this asserts on
STATE and EMISSIONS instead, so it survives cosmetic layout changes and pins
the actual interaction semantics.

Behaviors asserted:
- typing narrows the filtered match count
- backspace widens the filtered match count
- escape clears both the search query and the text-input state
- up/down wrap the selection over the filtered length
- enter sets `picked` to the current selection
- tab cycles the filter mode, clamping selection when the match count shrinks

State fields verified-exist by reading source:
- `app.search` (painted Search) with `.query`/`.selected`
  (src/painted/search.py:16-17)
- `app.input_state` (TextInputState) with `.text`
  (src/painted/views/components/text_input.py:16)
- `app.filter_idx` and the `_filter_name`/`_filtered()` helpers
  (demos/apps/search_filter.py:79, 88-94)
- `app.picked` (demos/apps/search_filter.py:80)

`TestSurface` is driven exactly as the old golden drove it (same import
pattern, same key sequences); we read final state off the app instance after
`run_to_completion()` and use frame text only for one structural marker.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from painted.tui import TestSurface

_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_app_search_filter_unit",
    _PROJECT / "demos" / "apps" / "search_filter.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

SearchFilterApp = _mod.SearchFilterApp


def _drive(keys: list[str]) -> tuple[SearchFilterApp, list]:
    """Replay keys through a fresh app; return (app, frames)."""
    app = SearchFilterApp()
    harness = TestSurface(app, width=60, height=20, input_queue=keys)
    frames = harness.run_to_completion()
    return app, frames


def test_typing_narrows_match_count() -> None:
    # Fuzzy filter: "" -> 20, "d" -> 7, "de" -> 5, "dep" -> 3 (monotone narrowing).
    counts = []
    for keys in ([], list("d"), list("de"), list("dep")):
        app, _ = _drive(keys)
        counts.append(len(app._filtered()))
    assert counts == sorted(counts, reverse=True)
    assert counts[0] == len(app.items)  # empty query matches everything
    assert counts[-1] < counts[0]  # typing strictly narrowed
    # query state tracks the keystrokes
    assert app.search.query == "dep"
    assert app.input_state.text == "dep"


def test_backspace_widens_match_count() -> None:
    narrow, _ = _drive(list("dep"))
    wide, _ = _drive(list("dep") + ["backspace"])
    assert len(wide._filtered()) > len(narrow._filtered())
    assert wide.search.query == "de"
    assert wide.input_state.text == "de"


def test_escape_clears_query_and_input_state() -> None:
    app, _ = _drive(list("xyz") + ["escape"])
    assert app.search.query == ""
    assert app.search.selected == 0
    assert app.input_state.text == ""
    # escape resets to a fresh TextInputState (cursor home too)
    assert app.input_state.cursor == 0
    # cleared query matches everything again
    assert len(app._filtered()) == len(app.items)


def test_down_up_wrap_selection_over_filtered_length() -> None:
    # "de" yields 5 fuzzy matches. down x5 wraps back to 0; one up from 0 wraps to last.
    base = list("de")
    n = len(_drive(base)[0]._filtered())

    wrapped_down, _ = _drive(base + ["down"] * n)
    assert wrapped_down.search.selected == 0

    wrapped_up, _ = _drive(base + ["up"])
    assert wrapped_up.search.selected == n - 1

    # selection always stays within the filtered range
    walk, _ = _drive(base + ["down", "down", "up"])
    assert 0 <= walk.search.selected < n


def test_enter_picks_current_selection() -> None:
    app, _ = _drive(list("run") + ["down", "enter"])
    matches = app._filtered()
    expected = matches[app.search.selected]
    assert app.picked == expected
    assert app.picked != ""  # something was actually picked


def test_enter_on_no_matches_picks_nothing() -> None:
    app, _ = _drive(list("xyz") + ["enter"])
    assert app._filtered() == ()
    assert app.picked == ""  # selected_item is None, picked untouched


def test_tab_cycles_filter_mode() -> None:
    app, _ = _drive(["tab"])
    assert app.filter_idx == 1
    assert app._filter_name == "contains"
    app2, _ = _drive(["tab", "tab"])
    assert app2.filter_idx == 2
    assert app2._filter_name == "prefix"
    # cycles back to start
    app3, _ = _drive(["tab", "tab", "tab"])
    assert app3.filter_idx == 0
    assert app3._filter_name == "fuzzy"


def test_tab_clamps_selection_when_match_count_shrinks() -> None:
    # "re": fuzzy -> 6 matches, contains -> 4. Select index 5 under fuzzy, then
    # tab to contains: selected (5) >= new match count (4) must clamp to 0.
    base = list("re")
    pre_tab, _ = _drive(base + ["down"] * 5)
    assert pre_tab.search.selected == 5
    assert len(pre_tab._filtered()) == 6

    app, _ = _drive(base + ["down"] * 5 + ["tab"])
    assert app._filter_name == "contains"
    assert len(app._filtered()) == 4  # mode switch shrank the match set
    assert app.search.selected == 0  # clamped
    # query is preserved across the mode switch
    assert app.search.query == "re"


def test_emissions_record_every_key() -> None:
    keys = list("de") + ["down", "enter"]
    app = SearchFilterApp()
    harness = TestSurface(app, width=60, height=20, input_queue=keys)
    harness.run_to_completion()
    key_emissions = [data["key"] for kind, data in harness.emissions if kind == "ui.key"]
    assert key_emissions == keys


def test_structural_marker_present_in_frame() -> None:
    # One frame-text assertion: the header label is a stable structural anchor.
    _, frames = _drive([])
    assert "Search Filter" in frames[0].text
