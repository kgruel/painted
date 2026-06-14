"""Component width/proportionality laws — progress_bar fills exactly its budget.

`progress_bar` is the component whose correctness is a tiling claim, not just a
width claim: for any value and width it must lay down exactly `round(value*width)`
filled cells and `width - that` empty cells — they tile the budget with no gap and
no overflow — and that filled count must be monotonic in value. The demo-golden
that used to "cover" this saw only stripped characters; here the law is fuzzed.

(Bar-fill is the component-level cousin of the width-exactness laws in
`test_lens_width.py`; progress_bar both honors `width` and partitions it.)
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted.core.span import Line
from painted.views import AUTO, Column, Fill, ProgressState, current_icons, progress_bar
from painted.views.components._table import resolve_column_widths

_ratio = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_width = st.integers(min_value=1, max_value=120)


def _fill_counts(value: float, width: int) -> tuple[int, int, int]:
    """Return (filled, empty, total) cell counts for a rendered bar.

    Ambient icons are pinned to defaults by the suite-wide reset fixture, so
    current_icons() gives the chars progress_bar actually used.
    """
    ic = current_icons()
    block = progress_bar(ProgressState(value=value), width)
    chars = [cell.char for cell in block.row(0)]
    filled = sum(1 for ch in chars if ch == ic.progress_fill)
    empty = sum(1 for ch in chars if ch == ic.progress_empty)
    return filled, empty, block.width


@given(value=_ratio, width=_width)
def test_progress_bar_tiles_width_exactly(value: float, width: int) -> None:
    filled, empty, block_width = _fill_counts(value, width)
    assert block_width == width  # honors width
    assert filled + empty == width  # filled+empty tile the budget, no gap/overflow
    assert filled == round(value * width)  # filled tracks the value proportionally


@given(width=_width, a=_ratio, b=_ratio)
def test_progress_bar_fill_is_monotonic_in_value(width: int, a: float, b: float) -> None:
    lo, hi = (a, b) if a <= b else (b, a)
    filled_lo, _, _ = _fill_counts(lo, width)
    filled_hi, _, _ = _fill_counts(hi, width)
    assert filled_lo <= filled_hi


# -- Responsive column-width laws -------------------------------------------
#
# Fill columns are the table-level cousin of progress_bar: given a budget, the
# Fill tracks must tile whatever space remains exactly — no gap, no overflow —
# regardless of how the weights divide. The largest-remainder split is what
# makes integer widths sum back to the budget; this fuzzes that claim.

_weights = st.lists(st.integers(min_value=1, max_value=6), min_size=1, max_size=8)


@st.composite
def _columns(draw: st.DrawFn) -> list[Column]:
    """A small mix of fixed / AUTO / Fill columns with optional max caps."""
    track = st.one_of(
        st.integers(min_value=0, max_value=40),
        st.just(AUTO),
        st.builds(Fill, weight=st.integers(min_value=1, max_value=5)),
    )
    n = draw(st.integers(min_value=1, max_value=6))
    return [
        Column(
            header=Line.plain(draw(st.text(max_size=8))),
            width=draw(track),
            max_width=draw(st.one_of(st.none(), st.integers(min_value=1, max_value=50))),
        )
        for _ in range(n)
    ]


@given(weights=_weights, col_budget=st.integers(min_value=1, max_value=300))
def test_fill_columns_tile_budget_exactly(weights: list[int], col_budget: int) -> None:
    cols = [Column(header=Line.plain(""), width=Fill(weight=w)) for w in weights]
    rows = [[Line.plain("") for _ in weights]]
    sep_total = len(weights) - 1
    widths = resolve_column_widths(cols, rows, available=col_budget + sep_total)
    assert all(w >= 0 for w in widths)
    assert sum(widths) == col_budget  # fills tile the column budget, no gap/overflow


@given(cols=_columns(), available=st.one_of(st.none(), st.integers(min_value=0, max_value=300)))
def test_widths_are_nonnegative_and_respect_max(cols: list[Column], available) -> None:
    rows = [[Line.plain("x" * 12) for _ in cols]]
    widths = resolve_column_widths(cols, rows, available)
    assert len(widths) == len(cols)
    for col, w in zip(cols, widths):
        assert w >= 0
        if col.max_width is not None:
            assert w <= col.max_width  # max is the final clamp, always honored


@given(cols=_columns(), available=st.integers(min_value=0, max_value=300))
def test_resolution_is_deterministic(cols: list[Column], available: int) -> None:
    rows = [[Line.plain("data") for _ in cols]]
    assert resolve_column_widths(cols, rows, available) == resolve_column_widths(
        cols, rows, available
    )
