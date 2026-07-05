"""Property tier — wide-pair row traversal (`_row_ops`).

iter_row_spans / take_row_prefix / row_visible_text are the layer that paint()
and truncate() rely on to treat a wide glyph (lead + space placeholder) as one
atomic unit. A bug here silently mis-renders every wide character. These laws
verify the traversal is total, order-preserving, and budget-respecting — even on
deliberately malformed rows, where iter_row_spans must degrade to single-cell
spans rather than skip or duplicate cells.
"""

from __future__ import annotations

from hypothesis import assume, given
from hypothesis import strategies as st

from painted.core._row_ops import iter_row_spans, row_visible_text, take_row_prefix
from painted.core._text_width import char_width, display_width
from painted.core.block import _cells_from_text
from painted.core.cell import Cell, Style

from tests.property.strategies import text_st

_S = Style()
_RAW_CELLS = [Cell("a", _S), Cell("世", _S), Cell(" ", _S), Cell("→", _S), Cell("界", _S)]


def well_formed_rows() -> st.SearchStrategy[tuple[Cell, ...]]:
    """Rows produced the way Block does — valid wide pairs, no orphans."""
    return text_st(max_size=20).map(lambda t: tuple(_cells_from_text(t, _S)))


def any_rows() -> st.SearchStrategy[tuple[Cell, ...]]:
    """Well-formed rows OR hand-built arbitrary cell tuples (incl. orphan wides)."""
    malformed = st.lists(st.sampled_from(_RAW_CELLS), max_size=10).map(tuple)
    return st.one_of(well_formed_rows(), malformed)


@given(row=any_rows())
def test_iter_row_spans_covers_row_exactly_once(row) -> None:
    """Spans concatenate back to the row in order; widths classify cell count."""
    spans = list(iter_row_spans(row))
    reconstructed = tuple(c for s in spans for c in s.cells)
    assert reconstructed == tuple(row)
    assert sum(len(s.cells) for s in spans) == len(row)
    for s in spans:
        assert (s.width == 2) == (len(s.cells) == 2)


@given(row=any_rows(), mw=st.integers(min_value=0, max_value=20))
def test_take_row_prefix_no_split_within_budget(row, mw: int) -> None:
    """A row prefix stays within budget, is a real prefix, and keeps spans whole."""
    cells, _refs, used = take_row_prefix(row, mw)
    assert used <= mw
    assert tuple(cells) == tuple(row[: len(cells)])
    assert sum(s.width for s in iter_row_spans(tuple(cells))) == used


@given(row=well_formed_rows())
def test_row_visible_text_drops_only_placeholders(row) -> None:
    """Visible text width == summed span width (placeholders dropped, glyphs kept)."""
    # Vacuous only on degenerate rows; printable well-formed rows are the contract.
    assume(all(char_width(c.char) != 1 or c.char.isprintable() for c in row))
    txt = row_visible_text(row)
    assert display_width(txt) == sum(s.width for s in iter_row_spans(row))
