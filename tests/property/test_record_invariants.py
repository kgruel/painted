"""Property tier — record_line invariants (generalizes the seeded newline regression).

CRITICAL: `record_line(...).width == width` is NOT universally true. At FULL the
untruncated header grows past `width`; at SUMMARY/DETAILED a short summary
under-fills (the content segment is `Block.text(content_str)` with no width arg).
So the universally-quantified laws are:
  (a) the block is always rectangular (every row == block.width),
  (b) no embedded-newline cell at MINIMAL/SUMMARY/DETAILED, and FULL fans
      multiline values into real rows,
  (c) MINIMAL is a single row and honors width exactly (Block.text(width=width)).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted import Zoom
from painted.views import (
    apply_gutter,
    gutter_freshness,
    gutter_lifecycle,
    gutter_pass_fail,
    record_line,
)

from tests.helpers import block_to_text
from tests.property.strategies import MIXED_ALPHABET, no_id_blocks, text_st

_WELL_KNOWN = ["message", "summary", "output", "status", "detail", "description"]
_KINDS = ["task", "error", "decision", "log", "tick"]


def _record_payloads() -> st.SearchStrategy[dict]:
    keys = st.one_of(st.sampled_from(_WELL_KNOWN), text_st(max_size=8))
    vals = st.text(alphabet=MIXED_ALPHABET + "\n", max_size=20)
    return st.dictionaries(keys, vals, max_size=5)


def _newline_payloads() -> st.SearchStrategy[dict]:
    """Payloads with guaranteed multiline ASCII values (clean substring checks)."""
    line = st.text(alphabet="abcdef0123", min_size=1, max_size=6)
    multiline = st.lists(line, min_size=2, max_size=4).map("\n".join)
    return st.dictionaries(
        st.sampled_from(["message", "output"]), multiline, min_size=1, max_size=2
    )


@given(
    zoom=st.sampled_from(list(Zoom)),
    kind=st.sampled_from(_KINDS),
    payload=_record_payloads(),
    width=st.integers(min_value=10, max_value=80),
    ts=st.datetimes(),
)
def test_record_line_rectangular_all_zoom(zoom, kind, payload, width, ts) -> None:
    b = record_line(ts, kind, payload, zoom, width)
    for y in range(b.height):
        assert len(b.row(y)) == b.width


@given(
    zoom=st.sampled_from([Zoom.MINIMAL, Zoom.SUMMARY, Zoom.DETAILED]),
    payload=_newline_payloads(),
    width=st.integers(min_value=20, max_value=80),
    kind=st.sampled_from(["log", "task", "error"]),
    ts=st.datetimes(),
)
def test_record_line_no_embedded_newline_minimal_summary_detailed(
    zoom, payload, width, kind, ts
) -> None:
    b = record_line(ts, kind, payload, zoom, width)
    for y in range(b.height):
        for cell in b.row(y):
            assert cell.char != "\n"


@given(
    payload=_newline_payloads(),
    width=st.integers(min_value=20, max_value=80),
    kind=st.sampled_from(["log", "task"]),
    ts=st.datetimes(),
)
def test_record_line_full_splits_multiline_no_newline_cells(payload, width, kind, ts) -> None:
    b = record_line(ts, kind, payload, Zoom.FULL, width)
    for y in range(b.height):
        for cell in b.row(y):
            assert cell.char != "\n"
    text = block_to_text(b)
    for value in payload.values():
        for line in str(value).splitlines():
            assert line in text


@given(
    kind=st.sampled_from(_KINDS),
    payload=_record_payloads(),
    width=st.integers(min_value=10, max_value=80),
    ts=st.datetimes(),
)
def test_record_line_minimal_single_row_honors_width(kind, payload, width, ts) -> None:
    b = record_line(ts, kind, payload, Zoom.MINIMAL, width)
    assert b.height == 1
    assert b.width == width


@given(
    block=no_id_blocks(min_w=1, max_h=10),
    kind=st.sampled_from(["task", "error"]),
    payload=_record_payloads(),
    gutter_fn=st.sampled_from([gutter_lifecycle, gutter_freshness, gutter_pass_fail]),
)
def test_apply_gutter_adds_two_columns(block, kind, payload, gutter_fn) -> None:
    r = apply_gutter(block, kind, payload, gutter_fn)
    assert r.width == block.width + 2
    assert r.height == block.height
    for y in range(r.height):
        assert len(r.row(y)) == r.width
