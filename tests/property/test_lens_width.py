"""Property tier — lens width contract (generalizes the seeded chart regression).

Every lens honors width EXACTLY for ALL data shapes and zoom levels:
`lens(data, zoom=z, width=w).width == w` for w>=1. Lenses build via join_* and
manual `Block(row, width)` on recursive calls, so a width-loss (under-fill) or
width-gain (overflow) bug is plausible and invisible to the constructor (which
would instead raise on a ragged row — still caught here, as an error). This is
the "honors width" half of painted's width contract (see docs/PRIMITIVES.md).
"""

from __future__ import annotations

from hypothesis import example, given
from hypothesis import strategies as st

from painted.views import chart_lens, flame_lens, shape_lens, tree_lens
from painted.views.lens.shape import transcribe

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

# transcribe() shares shape_lens's built-in width machinery but adds two shapes
# the inferring path never reaches as its default (tuple items, frozenset tags),
# and recurses as transcription. Mirror _shape_data and fold both in so the
# width contract is stressed on transcribe's own payload space.
_transcribe_data = st.one_of(
    st.recursive(
        st.one_of(st.none(), st.booleans(), text_st(max_size=8), st.integers(), _numbers),
        lambda children: st.one_of(
            st.lists(children, max_size=5),
            st.lists(children, max_size=5).map(tuple),  # tuple payloads
            st.dictionaries(text_st(max_size=6), children, max_size=5),
        ),
        max_leaves=15,
    ),
    st.sets(st.one_of(st.integers(), st.text(alphabet=MIXED_ALPHABET, max_size=5)), max_size=5),
    st.frozensets(st.integers(), max_size=5),
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
    w=st.integers(min_value=1, max_value=80),
)
# The gate runs derandomize=True (no exploration), so the narrow-width corners the
# old floor guards covered must be PINNED — sampling will not re-find them. These
# four are the exact inputs that overflowed (string list -> 3, nested list -> 5);
# w=4 nested is the closest miss (5 vs 4), the highest-teeth example.
@example(data=["x", "y", "z"], z=2, w=1)
@example(data=["x", "y", "z"], z=3, w=2)
@example(data=[[None]], z=3, w=1)
@example(data=[[None]], z=3, w=4)
def test_shape_lens_honors_width(data, z: int, w: int) -> None:
    # Exact for every shape down to width 1. The list branch used to overflow its
    # budget at narrow widths by summing an unbudgeted "- " prefix onto floored
    # content; the contract is now exact, enforced here with no carve-out.
    assert shape_lens(data, zoom=z, width=w).width == w


@given(
    data=_transcribe_data,
    z=st.integers(min_value=0, max_value=3),
    w=st.integers(min_value=1, max_value=80),
)
# Same derandomized-gate reasoning as shape_lens: the narrow-width corners must be
# PINNED, here on transcribe's extra payloads (tuple items, nested tuples) so the
# "- " prefix budgeting is exercised on the tuple path too.
@example(data=("x", "y", "z"), z=2, w=1)
@example(data=("x", "y", "z"), z=3, w=2)
@example(data=((None,),), z=3, w=1)
@example(data=((None,),), z=3, w=4)
def test_transcribe_honors_width(data, z: int, w: int) -> None:
    # transcribe() is paint()'s no-lens default (never inferring): it must honor
    # width exactly across every declared shape — including tuples and frozensets,
    # which the inferring shape_lens strategy above does not cover.
    assert transcribe(data, zoom=z, width=w).width == w
