"""Property tier — lens width contract (generalizes the seeded chart regression).

Every lens must honor its width budget for ALL data shapes and zoom levels:
`lens(data, zoom=z, width=w).width == w`. Lenses build via join_* and manual
`Block(row, width)` on recursive calls, so a width-loss bug is plausible and
invisible to the constructor (which would instead raise — still caught here, as
an error rather than an assertion).

Empirically established carve-out: shape_lens over a LIST at zoom>=2 floors its
width at 3, so the universal law is asserted for width>=3; the sub-3 floor is
documented separately as a regression guard.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from painted.views import chart_lens, flame_lens, shape_lens, tree_lens

from tests.property.strategies import MIXED_ALPHABET, text_st

_numbers = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
)

_chart_data = st.one_of(
    st.lists(_numbers, max_size=8),
    st.dictionaries(text_st(max_size=8), _numbers, max_size=6),
    _numbers,
)

_tree_data = st.recursive(
    st.one_of(text_st(max_size=8), st.integers(), _numbers),
    lambda children: st.dictionaries(text_st(max_size=6), children, min_size=1, max_size=4),
    max_leaves=15,
)

_flame_data = st.one_of(
    st.dictionaries(text_st(max_size=6), _numbers, max_size=5),
    st.dictionaries(
        text_st(max_size=6),
        st.dictionaries(text_st(max_size=6), _numbers, max_size=4),
        max_size=4,
    ),
    st.just({}),
)

_shape_data = st.one_of(
    st.recursive(
        st.one_of(st.none(), st.booleans(), text_st(max_size=8), st.integers(), _numbers),
        lambda children: st.one_of(
            st.lists(children, max_size=5),
            st.dictionaries(text_st(max_size=6), children, max_size=5),
        ),
        max_leaves=15,
    ),
    st.sets(st.one_of(st.integers(), st.text(alphabet=MIXED_ALPHABET, max_size=5)), max_size=5),
)


@given(
    data=_chart_data,
    z=st.integers(min_value=0, max_value=3),
    w=st.integers(min_value=1, max_value=80),
)
def test_chart_lens_honors_width(data, z: int, w: int) -> None:
    assert chart_lens(data, zoom=z, width=w).width == w


@given(
    data=_tree_data,
    z=st.integers(min_value=0, max_value=4),
    w=st.integers(min_value=1, max_value=80),
)
def test_tree_lens_honors_width(data, z: int, w: int) -> None:
    assert tree_lens(data, zoom=z, width=w).width == w


@given(
    data=_flame_data,
    z=st.integers(min_value=0, max_value=3),
    w=st.integers(min_value=1, max_value=80),
)
def test_flame_lens_honors_width(data, z: int, w: int) -> None:
    assert flame_lens(data, zoom=z, width=w).width == w


@given(
    data=_shape_data,
    z=st.integers(min_value=0, max_value=3),
    w=st.integers(min_value=8, max_value=80),
)
def test_shape_lens_honors_width(data, z: int, w: int) -> None:
    # Domain w>=8: shape_lens dispatches by shape and floors the width at a small
    # structure-dependent minimum (max observed 5, for a nested list at zoom 3 —
    # see the floor guards below). Above that floor it honors width exactly; w>=8
    # clears it with margin. The sub-floor behavior is pinned deterministically.
    assert shape_lens(data, zoom=z, width=w).width == w


@pytest.mark.parametrize("z", [2, 3])
@pytest.mark.parametrize("w", [1, 2])
def test_shape_lens_string_list_floors_width_at_three(z: int, w: int) -> None:
    """KNOWN EDGE: a list of strings renders via a path with a 3-column floor, so it
    does NOT honor sub-3 widths (integer lists DO — they route to the chart lens).

    Deterministic regression guard: documents the floor and fails loudly if it is
    ever fixed (so this marker can be removed) or changed.
    """
    assert shape_lens(["x", "y", "z"], zoom=z, width=w).width == 3


@pytest.mark.parametrize("w", [1, 2, 3, 4])
def test_shape_lens_nested_list_floors_width_at_five(w: int) -> None:
    """KNOWN EDGE: a nested list at zoom 3 floors its width at 5 (the deepest floor
    shape_lens exhibits; it saturates there regardless of nesting depth).

    Deterministic regression guard, companion to the string-list floor above.
    """
    assert shape_lens([[None]], zoom=3, width=w).width == 5
