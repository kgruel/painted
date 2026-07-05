"""Property tier — the ``series`` digest is deterministic and in-range.

Open sets (chart lines, observers, ``overflow="series"`` members) get a stable
color from ``series_index`` / ``Palette.series_for``: the same key must land on
the same ramp position in every process and every session (design doc §5). This
is the invariant that makes ``series`` honest — builtin ``hash()`` fails it under
``PYTHONHASHSEED`` randomization.

Two laws under Hypothesis, plus a golden pin. The pin freezes a few fixed keys to
their indices under the default ramp, so any change to the digest (md5, the
8-byte slice, or the modulus) shows up as a loud, deliberate edit to this file —
not a silent recoloring of every consumer.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted.palette import DEFAULT_PALETTE, series_index

from tests.property.strategies import text_st


@given(key=text_st(max_size=40), count=st.integers(min_value=1, max_value=64))
def test_series_index_in_range(key: str, count: int) -> None:
    assert 0 <= series_index(key, count) < count


@given(key=text_st(max_size=40), count=st.integers(min_value=-4, max_value=0))
def test_series_index_nonpositive_count_is_zero(key: str, count: int) -> None:
    # An empty ramp has no position; the guard returns 0 rather than dividing by
    # zero (series_for turns this into a bare Style()).
    assert series_index(key, count) == 0


@given(key=text_st(max_size=40), count=st.integers(min_value=1, max_value=64))
def test_series_index_is_deterministic(key: str, count: int) -> None:
    # Same key, same index, across repeated calls — no per-process seed.
    assert series_index(key, count) == series_index(key, count)


@given(key=text_st(max_size=40))
def test_series_for_matches_index(key: str) -> None:
    ramp = DEFAULT_PALETTE.series
    assert DEFAULT_PALETTE.series_for(key) == ramp[series_index(key, len(ramp))]


def test_series_index_golden_pins() -> None:
    """Fixed keys → pinned indices under the default 4-style ramp.

    A change here means the digest changed. That is allowed, but it recolors
    every open set in every downstream program — so it must be a conscious edit,
    reviewed in the diff, not an accident.
    """
    assert len(DEFAULT_PALETTE.series) == 4
    pins = {"green": 0, "two": 1, "red": 2, "one": 3}
    for key, expected in pins.items():
        assert series_index(key, 4) == expected


def test_series_for_empty_ramp_is_bare_style() -> None:
    from painted import Palette, Style

    empty = Palette(series=())
    assert empty.series_for("anything") == Style()
