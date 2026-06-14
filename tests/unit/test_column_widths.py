"""Tests for responsive column-width resolution (resolve_column_widths).

The resolver is the pre-pass that turns each column's track-sizing function
(fixed ``int`` / ``AUTO`` / ``Fill``) into an exact integer width before the
table lays out cells. These tests pin the resolution rules directly; the
rendered-table integration lives in test_table_render.py.
"""

from __future__ import annotations

from painted.core.span import Line
from painted.views import AUTO, Column, Fill
from painted.views.components._table import resolve_column_widths


def _col(width, header: str = "", *, min_width=None, max_width=None) -> Column:
    return Column(header=Line.plain(header), width=width, min_width=min_width, max_width=max_width)


def _rows(*rows: list[str]) -> list[list[Line]]:
    return [[Line.plain(cell) for cell in row] for row in rows]


class TestFixedAndAuto:
    def test_fixed_passthrough_no_budget(self) -> None:
        cols = [_col(5), _col(8), _col(3)]
        assert resolve_column_widths(cols, _rows(["x", "y", "z"]), None) == [5, 8, 3]

    def test_fixed_ignores_budget(self) -> None:
        # Fixed columns are not responsive — the budget doesn't move them.
        cols = [_col(5), _col(8)]
        assert resolve_column_widths(cols, _rows(["x", "y"]), available=80) == [5, 8]

    def test_auto_sizes_to_content(self) -> None:
        cols = [_col(AUTO, "Name"), _col(AUTO, "Age")]
        rows = _rows(["Alice", "30"], ["Bob", "25"])
        # col0: max(len("Name")=4, "Alice"=5, "Bob"=3) = 5; col1: max("Age"=3, ...) = 3
        assert resolve_column_widths(cols, rows, None) == [5, 3]

    def test_auto_header_wins_when_widest(self) -> None:
        cols = [_col(AUTO, "LongHeader")]
        assert resolve_column_widths(cols, _rows(["x"]), None) == [10]

    def test_auto_measures_display_width_not_len(self) -> None:
        # "你好" is 2 codepoints but 4 display columns — the win over siftd's len().
        cols = [_col(AUTO, "")]
        assert resolve_column_widths(cols, _rows(["你好"]), None) == [4]


class TestFill:
    def test_single_fill_eats_leftover(self) -> None:
        # available 20, one separator -> 19 for columns; fixed 5 -> fill = 14.
        cols = [_col(5), _col(Fill())]
        assert resolve_column_widths(cols, _rows(["x", "y"]), available=20) == [5, 14]

    def test_two_fills_split_evenly(self) -> None:
        # available 21, one sep -> 20 for columns; two equal fills -> 10 each.
        cols = [_col(Fill()), _col(Fill())]
        assert resolve_column_widths(cols, _rows(["a", "b"]), available=21) == [10, 10]

    def test_weighted_fill_split(self) -> None:
        # leftover 20 across weights 1 and 3 -> 5 and 15.
        cols = [_col(Fill(weight=1)), _col(Fill(weight=3))]
        assert resolve_column_widths(cols, _rows(["a", "b"]), available=21) == [5, 15]

    def test_largest_remainder_is_deterministic(self) -> None:
        # leftover 10 across three equal fills: 3 each + 1 spare -> lowest index.
        cols = [_col(Fill()), _col(Fill()), _col(Fill())]
        widths = resolve_column_widths(cols, _rows(["a", "b", "c"]), available=12)
        assert widths == [4, 3, 3]
        assert sum(widths) == 10

    def test_fill_fills_budget_exactly(self) -> None:
        cols = [_col(7), _col(Fill()), _col(Fill(weight=2))]
        widths = resolve_column_widths(cols, _rows(["a", "b", "c"]), available=50)
        assert sum(widths) + (3 - 1) == 50  # columns + separators fill the budget


class TestMinMax:
    def test_auto_capped_at_max(self) -> None:
        cols = [_col(AUTO, "x", max_width=3)]
        assert resolve_column_widths(cols, _rows(["LongContent"]), None) == [3]

    def test_auto_floored_at_min(self) -> None:
        cols = [_col(AUTO, "x", min_width=10)]
        assert resolve_column_widths(cols, _rows(["hi"]), None) == [10]

    def test_fill_respects_min_when_no_room(self) -> None:
        # available smaller than the fixed column: fill drops to its min floor.
        cols = [_col(20), _col(Fill(), min_width=5)]
        assert resolve_column_widths(cols, _rows(["x", "y"]), available=10) == [20, 5]

    def test_fill_capped_at_max_under_fills(self) -> None:
        # A generous budget but a capped fill: the column stops at max, table under-fills.
        cols = [_col(Fill(), max_width=4)]
        assert resolve_column_widths(cols, _rows(["x"]), available=50) == [4]


class TestNoBudget:
    def test_fill_falls_back_to_natural(self) -> None:
        cols = [_col(AUTO, "Name"), _col(Fill(), "Notes")]
        rows = _rows(["Alice", "hello world"])
        # No budget -> Fill behaves like AUTO: col1 = max("Notes"=5, "hello world"=11).
        assert resolve_column_widths(cols, rows, None) == [5, 11]


class TestOverBudgetNoFill:
    def test_returns_unshrunk_widths(self) -> None:
        # All AUTO, content wider than budget, no Fill column to absorb it:
        # widths come back unshrunk (plan-a) — table() clips the assembled block.
        cols = [_col(AUTO, ""), _col(AUTO, "")]
        rows = _rows(["aaaaaaaaaa", "bbbbbbbbbb"])  # 10 + 10
        widths = resolve_column_widths(cols, rows, available=12)
        assert widths == [10, 10]
        assert sum(widths) > 12


class TestEdgeCases:
    def test_empty_columns(self) -> None:
        assert resolve_column_widths([], [], available=80) == []

    def test_rows_with_missing_cells_dont_break_natural(self) -> None:
        # A row shorter than the column count contributes nothing past its cells.
        cols = [_col(AUTO, "A"), _col(AUTO, "B")]
        rows = [[Line.plain("xxxx")]]  # only one cell for two columns
        assert resolve_column_widths(cols, rows, None) == [4, 1]
