"""Property tier — hardened shape_lens is cycle-safe and width-exact.

Slice 1 of the diagnostics arc threads cycle/depth state through shape_lens so the
error renderer can print arbitrary values (locals, payloads) without crashing. Two
laws, both under Hypothesis-generated *self-referential* structures (the case the
error renderer must survive — a cyclic local must never take down the traceback):

- **cycle-safety**: rendering any self-referential structure never raises (in
  particular never RecursionError), at any zoom including the high zooms that
  defeat the zoom-decrement bound.
- **width-exactness**: the width contract still holds — `.width == w` for w>=1 —
  even when the recursion terminates on a `↻ <cycle>` / `…` marker.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted.views import shape_lens

from tests.property.strategies import text_st

_leaf = st.one_of(st.none(), st.booleans(), text_st(max_size=6), st.integers())

# Acyclic nested containers; we splice a self-reference into these below.
_nested = st.recursive(
    _leaf,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(text_st(max_size=5), children, max_size=4),
    ),
    max_leaves=12,
)


@st.composite
def _self_referential(draw):
    """A container spliced to reference itself — the shape the guard must catch.

    Build a nested acyclic structure, then create a back-edge: a list appends
    itself, a dict points a key at itself. Non-container draws are wrapped so the
    result always carries a real cycle.
    """
    base = draw(_nested)
    if isinstance(base, list):
        base.append(base)
        return base
    if isinstance(base, dict):
        base["__self__"] = base
        return base
    # Leaf: wrap it so there is always a cycle to exercise.
    box: list = [base]
    box.append(box)
    return box


@st.composite
def _mutual_cycle(draw):
    """Two dicts referencing each other — a cycle no single-object guard catches
    by identity on the first visit alone."""
    a: dict = {"payload": draw(_leaf)}
    b: dict = {"payload": draw(_leaf)}
    a["b"] = b
    b["a"] = a
    return a


_cyclic = st.one_of(_self_referential(), _mutual_cycle())


@given(
    data=_cyclic,
    z=st.integers(min_value=0, max_value=64),
    w=st.integers(min_value=1, max_value=80),
)
def test_cyclic_shape_never_raises(data, z: int, w: int) -> None:
    # The only assertion that matters is that this returns — a RecursionError (the
    # bug this slice fixes) or any other exception fails the property.
    shape_lens(data, zoom=z, width=w)


@given(
    data=_cyclic,
    z=st.integers(min_value=0, max_value=64),
    w=st.integers(min_value=1, max_value=80),
)
def test_cyclic_shape_honors_width(data, z: int, w: int) -> None:
    # Width stays exact even when the recursion terminates on a marker.
    assert shape_lens(data, zoom=z, width=w).width == w
