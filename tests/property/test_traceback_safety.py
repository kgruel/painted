"""Property tier — render_traceback is width-exact and never raises.

The error renderer must survive whatever exception it is handed: arbitrary
messages, arbitrary widths, captured TracebackExceptions with synthetic frames. If
rendering an error can itself raise, it is worse than useless. Two laws:

- **never-raises**: rendering any exception at any zoom/width returns a Block.
- **width-exactness**: a passed int ``width`` is exact (``.width == w``, w>=1).
"""

from __future__ import annotations

import traceback

from hypothesis import given
from hypothesis import strategies as st

from painted.core.zoom import Zoom
from painted.views import render_traceback

from tests.property.strategies import text_st

_zoom = st.sampled_from([Zoom.MINIMAL, Zoom.SUMMARY, Zoom.DETAILED, Zoom.FULL])


def _raise(message: str) -> BaseException:
    try:
        raise ValueError(message)
    except ValueError as exc:
        return exc


@given(message=text_st(max_size=40), z=_zoom, w=st.integers(min_value=1, max_value=100))
def test_render_is_width_exact(message: str, z: Zoom, w: int) -> None:
    # Arbitrary (possibly newline/control-bearing) messages stay width-exact.
    assert render_traceback(_raise(message), z, w).width == w


@given(message=text_st(max_size=40), z=_zoom)
def test_render_never_raises(message: str, z: Zoom) -> None:
    # The only thing that matters is that it returns — natural width, no clip.
    render_traceback(_raise(message), z, None)


@given(message=text_st(max_size=40), z=_zoom, w=st.integers(min_value=1, max_value=100))
def test_tracebackexception_path_is_safe(message: str, z: Zoom, w: int) -> None:
    # The Fact-friendly boundary: a captured TracebackException renders identically
    # safely (width-exact, never raises).
    te = traceback.TracebackException.from_exception(_raise(message), capture_locals=True)
    assert render_traceback(te, z, w).width == w


@given(z=_zoom, w=st.integers(min_value=1, max_value=100))
def test_cause_cycle_never_raises(z: Zoom, w: int) -> None:
    # A cyclic __cause__ chain (legal via explicit assignment) must not recurse
    # forever — the walk stops at a muted cycle marker.
    a, b = _raise("a"), _raise("b")
    a.__cause__, b.__cause__ = b, a
    assert render_traceback(b, z, w).width == w


@given(z=_zoom, w=st.integers(min_value=1, max_value=100))
def test_context_cycle_never_raises(z: Zoom, w: int) -> None:
    # The same guard holds for a cyclic __context__ chain (re-raise/retry code).
    a, b = _raise("a"), _raise("b")
    a.__context__, b.__context__ = b, a
    a.__suppress_context__ = b.__suppress_context__ = False
    assert render_traceback(a, z, w).width == w


def test_self_cause_cycle_never_raises() -> None:
    # `raise e from e` is a one-node cycle — the tightest case.
    e = _raise("self")
    e.__cause__ = e
    render_traceback(e, Zoom.DETAILED, 80)
