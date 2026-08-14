"""Property tier — Span/Line styled-text primitives.

Line.to_block materializes through the shared run engine (`_wrap_runs` /
`_cells_from_runs` in block.py) — it once carried a parallel per-char loop that
could drift from `_cells_from_text`; these laws pinned that seam and now guard
the unified path's rectangle + wide-safety contract and Line.truncate's budget.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted import Block, Line, Span, Style, Wrap
from painted.core.cell import Cell

from tests.property.strategies import has_orphan_wide, styles, text_st


@st.composite
def lines_st(draw: st.DrawFn) -> Line:
    n = draw(st.integers(min_value=1, max_value=4))
    spans = tuple(Span(draw(text_st(max_size=10)), draw(styles())) for _ in range(n))
    return Line(spans=spans, style=draw(styles()))


def _cells(row: list[Cell]) -> list[tuple[str, Style]]:
    return [(c.char, c.style) for c in row]


@given(
    text=text_st(max_size=20),
    style=styles(),
    w=st.integers(min_value=1, max_value=20),
    mode=st.sampled_from(list(Wrap)),
)
def test_single_style_line_wrap_equals_block_text(
    text: str, style: Style, w: int, mode: Wrap
) -> None:
    """The unification's core safety claim: for a single-style Line, ``Line.wrap``
    is byte-identical to ``Block.text`` in every Wrap mode.

    ``Block.text`` is the uniform-style adapter over the same styled wrap engine
    ``Line.wrap`` drives, so the str path must agree with the styled path
    cell-for-cell (char *and* style) — pad cells and the ELLIPSIS marker
    included. A divergence here means the adapter has drifted from the engine."""
    line = Line((Span(text, Style()),), style=style)
    lw = line.wrap(w, wrap=mode)
    bt = Block.text(text, style, width=w, wrap=mode)
    assert (lw.height, lw.width) == (bt.height, bt.width)
    for y in range(bt.height):
        assert _cells(lw.row(y)) == _cells(bt.row(y))


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
