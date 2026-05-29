"""Property tier — width/truncation primitives (`_text_width`, `_cells_from_text`).

These underpin every higher-level width law. The teeth here are the 2-cell
wide-char expansion, combining-mark dropping, and max-width budget enforcement —
NOT wcwidth consistency (that would mostly re-test the wcwidth library).

See tests/property/strategies.py for why the alphabet is heavily non-ASCII and
excludes the zero-width joiner.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted.core._row_ops import iter_row_spans
from painted.core._text_width import (
    char_width,
    display_width,
    index_for_col,
    take_prefix,
    truncate_ellipsis,
)
from painted.core.block import _cells_from_text

from tests.property.strategies import has_orphan_wide, styles, text_st


@given(text=text_st(), style=styles())
def test_cells_from_text_cellcount_equals_display_width(text: str, style) -> None:
    """len(cells) == display_width(text): the cell-count == display-columns law.

    Proves in one equality that wide chars emit lead+placeholder (2 cells = 2
    cols), combining marks emit 0 cells (= 0 cols), and ASCII is 1:1. Cross-checks
    painted's cell construction against the independent wcswidth measurement.
    """
    assert len(_cells_from_text(text, style)) == display_width(text)


@given(text=text_st(), style=styles())
def test_cells_from_text_wide_char_has_placeholder(text: str, style) -> None:
    """Every wide cell is followed by a same-style space; no zero-width cell exists."""
    cells = _cells_from_text(text, style)
    for i, cell in enumerate(cells):
        assert char_width(cell.char) != 0, "combining/zero-width char leaked into a cell"
        if char_width(cell.char) == 2:
            assert i + 1 < len(cells), "wide lead cell with no placeholder"
            assert cells[i + 1].char == " "
            assert cells[i + 1].style == cell.style


@given(text=text_st(max_size=40), mw=st.integers(min_value=1, max_value=30), style=styles())
def test_cells_from_text_respects_max_width(text: str, mw: int, style) -> None:
    """A max_width prefix fits the budget in display columns and splits no wide char."""
    cells = tuple(_cells_from_text(text, style, max_width=mw))
    used = sum(span.width for span in iter_row_spans(cells))
    assert used <= mw
    assert not has_orphan_wide(cells)


@given(text=text_st(max_size=40), mw=st.integers(min_value=0, max_value=30))
def test_take_prefix_within_budget_no_split(text: str, mw: int) -> None:
    """take_prefix stays within budget, returns a real prefix, splits no wide char."""
    prefix, consumed = take_prefix(text, mw)
    assert display_width(prefix) <= mw
    assert prefix == text[:consumed]
    assert 0 <= consumed <= len(text)


@given(
    text=text_st(max_size=40),
    mw=st.integers(min_value=1, max_value=30),
    ell=st.sampled_from(["…", "..", "->", "世"]),
)
def test_truncate_ellipsis_within_budget(text: str, mw: int, ell: str) -> None:
    """truncate_ellipsis never exceeds the budget, for any ellipsis incl. width-2."""
    result = truncate_ellipsis(text, mw, ellipsis=ell)
    assert display_width(result) <= mw


@given(text=text_st(max_size=30), col=st.integers(min_value=0, max_value=30))
def test_index_for_col_within_bound(text: str, col: int) -> None:
    """index_for_col returns an index whose prefix fits col, bounded by len(text)."""
    i = index_for_col(text, col)
    assert 0 <= i <= len(text)
    assert display_width(text[:i]) <= col
