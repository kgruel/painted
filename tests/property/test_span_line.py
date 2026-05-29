"""Property tier — Span/Line styled-text primitives.

Line.to_block builds cells with its OWN wide-char + combining-drop logic
(span.py), a parallel implementation to `_cells_from_text` that can drift. These
laws pin its rectangle + wide-safety contract and Line.truncate's budget.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted import Line, Span

from tests.property.strategies import has_orphan_wide, styles, text_st


@st.composite
def lines_st(draw: st.DrawFn) -> Line:
    n = draw(st.integers(min_value=1, max_value=4))
    spans = tuple(Span(draw(text_st(max_size=10)), draw(styles())) for _ in range(n))
    return Line(spans=spans, style=draw(styles()))


@given(line=lines_st(), w=st.integers(min_value=1, max_value=30))
def test_line_to_block_rectangular_no_wide_split(line: Line, w: int) -> None:
    """Line.to_block(w): a single rectangular row of width w, no orphaned wide char."""
    b = line.to_block(w)
    assert b.height == 1
    assert b.width == w
    assert len(b.row(0)) == w
    assert not has_orphan_wide(b.row(0))


@given(line=lines_st(), mw=st.integers(min_value=0, max_value=30))
def test_line_truncate_within_budget(line: Line, mw: int) -> None:
    """Line.truncate(mw) never exceeds the budget nor grows past the original."""
    r = line.truncate(mw)
    assert r.width <= mw
    assert r.width <= line.width
