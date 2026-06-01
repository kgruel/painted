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

from painted.views import ProgressState, current_icons, progress_bar

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
