"""Tests for the table() render function."""

from __future__ import annotations

from painted import Align, Cursor, Style, Viewport
from painted.core.span import Line
from painted.views import AUTO, Column, EllipsisSide, Fill, Overflow, TableState, table
from tests.helpers import row_text


def _make_columns(headers: list[str], widths: list[int]) -> list[Column]:
    """Build Column list from header strings and widths."""
    return [Column(header=Line.plain(h), width=w) for h, w in zip(headers, widths)]


def _make_rows(data: list[list[str]]) -> list[list[Line]]:
    """Build row data from plain strings."""
    return [[Line.plain(cell) for cell in row] for row in data]


class TestBasicTableRendering:
    def test_single_column_single_row(self) -> None:
        cols = _make_columns(["Name"], [6])
        rows = _make_rows([["Alice"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=3)

        assert blk.height >= 3  # header + separator + at least 1 data row
        assert "Name" in row_text(blk, 0)
        assert "Alice" in row_text(blk, 2)

    def test_two_columns_with_separator(self) -> None:
        cols = _make_columns(["Name", "Age"], [6, 4])
        rows = _make_rows([["Alice", "30"], ["Bob", "25"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=3)

        header = row_text(blk, 0)
        assert "Name" in header
        assert "Age" in header
        assert "│" in header

    def test_multiple_rows_rendered(self) -> None:
        cols = _make_columns(["Item"], [10])
        rows = _make_rows([["apple"], ["banana"], ["cherry"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=5)

        assert "apple" in row_text(blk, 2)
        assert "banana" in row_text(blk, 3)
        assert "cherry" in row_text(blk, 4)


class TestSeparatorRow:
    def test_separator_uses_horizontal_lines(self) -> None:
        cols = _make_columns(["A", "B"], [4, 4])
        rows = _make_rows([["x", "y"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2)

        sep_row = row_text(blk, 1)
        assert "─" in sep_row
        assert "┼" in sep_row

    def test_single_column_separator_no_cross(self) -> None:
        cols = _make_columns(["Col"], [5])
        rows = _make_rows([["val"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2)

        sep_row = row_text(blk, 1)
        assert "─" in sep_row
        assert "┼" not in sep_row


class TestSelectedRowHighlighting:
    def test_first_row_selected_by_default(self) -> None:
        cols = _make_columns(["Name"], [6])
        rows = _make_rows([["Alice"], ["Bob"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=3)

        # Row 0 (buf_y=2) should have selected_style (reverse=True)
        first_data_row = blk.row(2)
        assert any(c.style.reverse for c in first_data_row)

    def test_second_row_not_selected_by_default(self) -> None:
        cols = _make_columns(["Name"], [6])
        rows = _make_rows([["Alice"], ["Bob"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=3)

        second_data_row = blk.row(3)
        assert not any(c.style.reverse for c in second_data_row)

    def test_moved_selection(self) -> None:
        cols = _make_columns(["Name"], [6])
        rows = _make_rows([["Alice"], ["Bob"], ["Carol"]])
        state = TableState(cursor=Cursor(index=1, count=3))

        blk = table(state, cols, rows, visible_height=5)

        # Row 0 (Alice) should not be selected
        assert not any(c.style.reverse for c in blk.row(2))
        # Row 1 (Bob) should be selected
        assert any(c.style.reverse for c in blk.row(3))

    def test_custom_selected_style(self) -> None:
        cols = _make_columns(["X"], [4])
        rows = _make_rows([["hi"]])
        state = TableState()
        custom = Style(bold=True)

        blk = table(state, cols, rows, visible_height=2, selected_style=custom)

        data_row = blk.row(2)
        assert any(c.style.bold for c in data_row)


class TestColumnWidthAllocation:
    def test_total_width_single_column(self) -> None:
        cols = _make_columns(["Name"], [10])
        rows = _make_rows([["test"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2)

        assert blk.width == 10

    def test_total_width_multiple_columns(self) -> None:
        cols = _make_columns(["A", "B", "C"], [5, 8, 3])
        rows = _make_rows([["x", "y", "z"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2)

        # 5 + 8 + 3 + 2 separators (1 char each) = 18
        assert blk.width == 18

    def test_short_content_padded(self) -> None:
        cols = _make_columns(["Name"], [10])
        rows = _make_rows([["Hi"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2)

        row_line = row_text(blk, 2)
        assert len(row_line) == 10
        assert row_line.startswith("Hi")

    def test_long_content_truncated(self) -> None:
        cols = _make_columns(["Name"], [4])
        rows = _make_rows([["VeryLongName"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2)

        row_line = row_text(blk, 2)
        assert len(row_line) == 4


class TestScrollingBehavior:
    def test_no_scroll_when_rows_fit(self) -> None:
        cols = _make_columns(["V"], [5])
        rows = _make_rows([["a"], ["b"], ["c"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=5)

        assert "a" in row_text(blk, 2)
        assert "b" in row_text(blk, 3)
        assert "c" in row_text(blk, 4)

    def test_scroll_offset_skips_rows(self) -> None:
        cols = _make_columns(["V"], [5])
        rows = _make_rows([["a"], ["b"], ["c"], ["d"], ["e"]])
        state = TableState(
            cursor=Cursor(index=3, count=5),
            viewport=Viewport(offset=2, visible=3, content=5),
        )

        blk = table(state, cols, rows, visible_height=3)

        # 5 rows overflow a height-3 window: the last body row is the law-6
        # evidence row (capacity 2), so the content window is rows c, d.
        assert "c" in row_text(blk, 2)
        assert "d" in row_text(blk, 3)
        assert "…" in row_text(blk, 4)  # evidence marker (text clipped at width 5)

    def test_scroll_shows_correct_selection(self) -> None:
        cols = _make_columns(["V"], [5])
        rows = _make_rows([["a"], ["b"], ["c"], ["d"], ["e"]])
        state = TableState(
            cursor=Cursor(index=3, count=5),
            viewport=Viewport(offset=2, visible=3, content=5),
        )

        blk = table(state, cols, rows, visible_height=3)

        # "d" is at index 3, visible at buf_y = 2 + (3-2) = 3
        assert any(c.style.reverse for c in blk.row(3))
        # "c" at buf_y=2 should not be selected
        assert not any(c.style.reverse for c in blk.row(2))


class TestEdgeCases:
    def test_empty_columns(self) -> None:
        state = TableState()
        blk = table(state, [], [], visible_height=3)

        assert blk.width == 1
        assert blk.height == 5  # empty(1, visible_height + 2)

    def test_empty_rows(self) -> None:
        cols = _make_columns(["Name"], [6])
        state = TableState()

        blk = table(state, cols, [], visible_height=3)

        assert "Name" in row_text(blk, 0)
        assert "─" in row_text(blk, 1)
        # Data area should be blank
        assert blk.height >= 3

    def test_rows_fewer_cells_than_columns(self) -> None:
        cols = _make_columns(["A", "B", "C"], [3, 3, 3])
        rows = [[Line.plain("x")]]  # Only 1 cell, but 3 columns
        state = TableState()

        blk = table(state, cols, rows, visible_height=2)

        data_text = row_text(blk, 2)
        assert "x" in data_text

    def test_custom_borders(self) -> None:
        from painted.core.borders import HEAVY

        cols = _make_columns(["A", "B"], [3, 3])
        rows = _make_rows([["x", "y"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2, borders=HEAVY)

        header = row_text(blk, 0)
        assert "┃" in header  # HEAVY vertical
        sep_row = row_text(blk, 1)
        assert "━" in sep_row  # HEAVY horizontal
        assert "╋" in sep_row  # HEAVY crossing

    def test_header_style_applied(self) -> None:
        cols = _make_columns(["Name"], [6])
        rows = _make_rows([["val"]])
        custom_header = Style(italic=True)
        state = TableState()

        blk = table(state, cols, rows, visible_height=2, header_style=custom_header)

        header_row = blk.row(0)
        assert any(c.style.italic for c in header_row)

    def test_block_height_matches_visible_plus_header(self) -> None:
        cols = _make_columns(["Col"], [5])
        rows = _make_rows([["a"], ["b"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=4)

        # header(1) + separator(1) + visible_height(4) = 6
        assert blk.height == 6


class TestColumnAlignment:
    def test_end_aligned_column(self) -> None:
        from painted.core.compose import Align

        cols = [Column(header=Line.plain("Num"), width=6, align=Align.END)]
        rows = _make_rows([["42"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2)

        data_text = row_text(blk, 2)
        # "42" should be right-aligned in a 6-wide column
        assert data_text.endswith("42") or data_text.rstrip() == "42"

    def test_center_aligned_column(self) -> None:
        from painted.core.compose import Align

        cols = [Column(header=Line.plain("Mid"), width=7, align=Align.CENTER)]
        rows = _make_rows([["hi"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2)

        data_text = row_text(blk, 2)
        stripped = data_text.strip()
        assert stripped == "hi"
        # Should have padding on both sides
        left_pad = len(data_text) - len(data_text.lstrip())
        right_pad = len(data_text) - len(data_text.rstrip())
        assert left_pad > 0
        assert right_pad > 0


class TestResponsiveColumns:
    def test_default_width_is_auto(self) -> None:
        # A column declared with no width sizes to its content.
        cols = [Column(header=Line.plain("Hdr"))]
        rows = _make_rows([["content"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2)

        assert blk.width == 7  # max(len("Hdr")=3, "content"=7)

    def test_auto_column_sizes_to_widest_cell(self) -> None:
        cols = [Column(header=Line.plain("X"), width=AUTO)]
        rows = _make_rows([["a"], ["abcdef"], ["abc"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=4)

        assert blk.width == 6

    def test_fill_column_fills_to_budget(self) -> None:
        cols = [
            Column(header=Line.plain("Name"), width=8),
            Column(header=Line.plain("Notes"), width=Fill()),
        ]
        rows = _make_rows([["Alice", "hi"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2, width=40)

        assert blk.width == 40  # 8 + 1 sep + 31 fill

    def test_fill_protects_auto_neighbor_when_narrow(self) -> None:
        # The vertices pattern: a sacrificial Fill column sheds while AUTO
        # columns keep their natural width. The marker stays, the brief gives way.
        from painted.core.compose import Align

        cols = [
            Column(header=Line.plain("name"), width=AUTO),
            Column(header=Line.plain("brief"), width=Fill()),
            Column(header=Line.plain("mark"), width=AUTO, align=Align.END),
        ]
        rows = _make_rows([["alpha", "a long brief that should shed first", "⊳"]])
        state = TableState()

        blk = table(state, cols, rows, visible_height=2, width=30)

        # The Fill column absorbs the squeeze so the table fits the budget exactly.
        assert blk.width == 30
        # The protected marker column keeps its natural (header) width.
        assert "mark" in row_text(blk, 0)


class TestOverflowFitRender:
    """End-to-end table() behavior under Overflow.FIT, including cell ellipsis."""

    def test_fit_does_not_balloon_when_it_fits(self) -> None:
        cols = [
            Column(header=Line.plain("day"), width=AUTO),
            Column(header=Line.plain("n"), width=Fill(), align=Align.END),
        ]
        rows = _make_rows([["2026-06-20", "5"]])
        blk = table(
            state=TableState(),
            columns=cols,
            rows=rows,
            visible_height=1,
            width=80,
            overflow=Overflow.FIT,
        )
        assert blk.width < 20  # compact, not stretched toward 80

    def test_fit_left_ellipsis_keeps_tail(self) -> None:
        cols = [
            Column(header=Line.plain("id"), width=AUTO),
            Column(
                header=Line.plain("ws"),
                width=Fill(),
                min_width=8,
                ellipsis=True,
                ellipsis_side=EllipsisSide.START,
            ),
        ]
        rows = _make_rows([["01ABCDEF1234", "-Users-kaygee-Code-siftd--7"]])
        blk = table(
            state=TableState(),
            columns=cols,
            rows=rows,
            visible_height=1,
            width=30,
            overflow=Overflow.FIT,
        )
        assert blk.width == 30
        cell = row_text(blk, 2)
        assert "…" in cell
        assert cell.rstrip().endswith("siftd--7")  # leaf survived

    def test_fit_end_ellipsis_keeps_head(self) -> None:
        """EllipsisSide.END (the default) keeps the head and marks the right."""
        cols = [
            Column(header=Line.plain("id"), width=AUTO),
            Column(
                header=Line.plain("desc"),
                width=Fill(),
                min_width=8,
                ellipsis=True,
                ellipsis_side=EllipsisSide.END,
            ),
        ]
        rows = _make_rows([["01ABCDEF1234", "a-long-description-that-overflows"]])
        blk = table(
            state=TableState(),
            columns=cols,
            rows=rows,
            visible_height=1,
            width=30,
            overflow=Overflow.FIT,
        )
        assert blk.width == 30
        cell = row_text(blk, 2)
        assert cell.rstrip().endswith("…")  # END: marker on the right
        assert "a-long-descript" in cell  # head survived (tail "overflows" dropped)
        assert "overflows" not in cell

    def test_fit_ellipsis_degrades_to_ascii(self) -> None:
        from painted.icon_set import ASCII_ICONS, reset_icons, use_icons

        cols = [
            Column(header=Line.plain("k"), width=AUTO),
            Column(header=Line.plain("desc"), width=Fill(), min_width=8, ellipsis=True),
        ]
        rows = _make_rows([["a", "Foreign key constraint violations in the main database"]])
        with use_icons(ASCII_ICONS):
            blk = table(
                state=TableState(),
                columns=cols,
                rows=rows,
                visible_height=1,
                width=30,
                overflow=Overflow.FIT,
            )
            cell = row_text(blk, 2)
            assert "…" not in cell
            assert "..." in cell  # ASCII marker
        reset_icons()

    def test_fit_right_ellipsis_keeps_head(self) -> None:
        cols = [
            Column(header=Line.plain("k"), width=AUTO),
            Column(header=Line.plain("desc"), width=Fill(), min_width=8, ellipsis=True),
        ]
        rows = _make_rows([["a", "Foreign key constraint violations in the main database"]])
        blk = table(
            state=TableState(),
            columns=cols,
            rows=rows,
            visible_height=1,
            width=30,
            overflow=Overflow.FIT,
        )
        assert blk.width == 30
        cell = row_text(blk, 2)
        assert cell.rstrip().endswith("…")  # head kept, marker on the right
        assert "Foreign key" in cell

    def test_fit_overflows_lossless_when_too_many_columns(self) -> None:
        cols = [
            Column(header=Line.plain("aa"), width=AUTO),
            Column(header=Line.plain("bb"), width=AUTO),
            Column(header=Line.plain("cc"), width=AUTO),
            Column(header=Line.plain("d"), width=Fill(), min_width=5),
        ]
        rows = _make_rows([["x" * 30, "y" * 30, "z" * 30, "w"]])
        blk = table(
            state=TableState(),
            columns=cols,
            rows=rows,
            visible_height=1,
            width=40,
            overflow=Overflow.FIT,
        )
        assert blk.width > 40  # not clipped to the budget
        header = row_text(blk, 0)
        for h in ("aa", "bb", "cc", "d"):
            assert h in header  # every column survives

    def test_clip_default_still_truncates_block(self) -> None:
        cols = [
            Column(header=Line.plain("a"), width=AUTO),
            Column(header=Line.plain("b"), width=AUTO),
        ]
        rows = _make_rows([["x" * 30, "y" * 30]])
        blk = table(state=TableState(), columns=cols, rows=rows, visible_height=1, width=20)
        assert blk.width == 20  # CLIP remains the default


class TestClipColumnBadge:
    """0.14 S2: the wholly-hidden-column badge under Overflow.CLIP.

    Two-armed law-6 pins live in tests/unit/test_render_model_laws.py
    (TestLaw6EvidencePins) — these are the component-local shape tests.
    """

    def test_two_wholly_hidden_columns_reserve_badge_inside_width(self) -> None:
        cols = _make_columns(["A", "B", "C"], [8, 8, 8])
        rows = _make_rows([["a" * 8, "b" * 8, "c" * 8]])

        blk = table(TableState(), cols, rows, visible_height=2, width=12)

        assert blk.width == 12  # honors-width: never exceeded
        header = row_text(blk, 0)
        assert "+2c" in header
        assert "B" not in header and "C" not in header

    def test_no_wholly_hidden_columns_no_badge(self) -> None:
        cols = _make_columns(["Item"], [20])
        rows = _make_rows([["v" * 20]])

        blk = table(TableState(), cols, rows, visible_height=2, width=12)

        assert blk.width == 12
        text = row_text(blk, 2)
        assert text.rstrip().endswith("…")
        assert "+" not in text

    def test_growing_the_badge_can_grow_the_count(self) -> None:
        # A column just past the plain-ellipsis cutoff can fall wholly behind
        # the wider badge-reserving cutoff — the fixed point must catch it.
        cols = _make_columns(["A", "B", "C", "D"], [10, 10, 10, 10])
        rows = _make_rows([["a" * 10, "b" * 10, "c" * 10, "d" * 10]])

        blk = table(TableState(), cols, rows, visible_height=2, width=15)

        header = row_text(blk, 0)
        assert "+3c" in header
        for letter in "BCD":
            assert letter not in header

    def test_fitting_table_is_unaffected(self) -> None:
        cols = _make_columns(["A", "B"], [5, 5])
        rows = _make_rows([["aaaaa", "bbbbb"]])

        fits = table(TableState(), cols, rows, visible_height=2, width=11)

        assert fits.width == 11
        blob = "\n".join(row_text(fits, y) for y in range(fits.height))
        assert "…" not in blob
        assert "+" not in blob
