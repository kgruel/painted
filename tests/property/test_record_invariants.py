"""Property tier — record_line invariants (generalizes the seeded newline regression).

record_line honors width EXACTLY at every zoom: `record_line(...).width == width`
(the "honors width" contract — see docs/PRIMITIVES.md). The universally-quantified
laws are:
  (a) width is exact at every zoom (block.width == width),
  (b) the block is always rectangular (every row == block.width),
  (c) no embedded-newline cell at MINIMAL/SUMMARY/DETAILED, and FULL fans
      multiline values into real rows,
  (d) MINIMAL is a single row,
  (e) FULL preserves complete data by WRAPPING wide values (grow height), not
      truncating — a value wider than `width` survives in full at exact width.
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
    record_line_composed,
    record_map,
    record_timeline,
)

from tests.helpers import block_to_text, row_text
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
    zoom=st.sampled_from(list(Zoom)),
    kind=st.sampled_from(_KINDS),
    payload=_record_payloads(),
    width=st.integers(min_value=10, max_value=80),
    ts=st.datetimes(),
)
def test_record_line_honors_width_all_zoom(zoom, kind, payload, width, ts) -> None:
    # The "honors width" contract: exact at EVERY zoom. Was false at
    # SUMMARY/DETAILED (under-fill: content segment built with no width arg) and
    # FULL (overflow: untruncated header/fields). See docs/PRIMITIVES.md.
    b = record_line(ts, kind, payload, zoom, width)
    assert b.width == width


@given(
    width=st.integers(min_value=30, max_value=70),
    kind=st.sampled_from(_KINDS),
    ts=st.datetimes(),
)
def test_record_line_full_wraps_wide_value_preserves_all_content(width, kind, ts) -> None:
    # FULL = data completeness AT exact width: a value far wider than `width` must
    # WRAP (grow height), never truncate. A "fit everything to width" fix that
    # truncated would pass exact-width yet silently drop data — this test forces
    # wrap, not truncate, by checking every marker char survives.
    b = record_line(ts, kind, {"message": "Z" * 200}, Zoom.FULL, width)
    assert b.width == width
    for y in range(b.height):
        assert len(b.row(y)) == b.width
    assert block_to_text(b).count("Z") >= 200


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


# The three shipped gutters are now declared over ``record_gutter``. A gutter
# renders arbitrary data: unknown categorical values route to the declared
# `unknown` fallback and numeric fields bucket through thresholds, so *no* payload
# value may raise or break the col-0 rail. Feed deliberately hostile status /
# age data and assert the rail stays continuous (a glyph on every row, never a
# space, never a shorter row).
# "Arbitrary" means arbitrary: not just hostile strings and out-of-range ints but
# the wrong TYPE entirely — None, NaN/±inf, nested structures (unhashable), bools.
# The old if-chains tolerated all of these; the factory must too (they route to the
# declared `unknown` fallback / the thresholds guard, never an exception).
_hostile_values = st.one_of(
    st.none(),
    st.text(max_size=12),
    st.integers(min_value=-(10**6), max_value=10**6),
    st.floats(allow_nan=True, allow_infinity=True),
    st.booleans(),
    st.lists(st.integers(), max_size=3),
    st.dictionaries(st.text(max_size=3), st.integers(), max_size=2),
)


@given(
    block=no_id_blocks(min_w=1, max_h=8),
    status=_hostile_values,
    age=_hostile_values,
    gutter_fn=st.sampled_from([gutter_lifecycle, gutter_freshness, gutter_pass_fail]),
)
def test_gutter_rail_continuous_across_arbitrary_payloads(block, status, age, gutter_fn) -> None:
    payload = {"status": status, "_age_days": age}
    r = apply_gutter(block, "task", payload, gutter_fn)  # must not raise
    assert r.height == block.height
    for y in range(r.height):
        assert len(r.row(y)) == r.width
        assert row_text(r, y)[0] != " "  # rail glyph present on every row


# --- Composition-level width law ---------------------------------------------
# record_line is exact, but the COMPOSERS are where the real misalignment annoyances
# live: apply_attention prepends an UNBUDGETED marker, apply_gutter adds 2, and
# headers/pads are natural-width. Each composer must honor its own width arg — the
# direct analog of the leaf law, one level up (where leaf-exactness does NOT just
# "propagate" through untested composition).


def _attn_high(kind: str, payload: dict) -> float:
    return 0.9


def _attn_mid(kind: str, payload: dict) -> float:
    return 0.5


def _attn_low(kind: str, payload: dict) -> float:
    return 0.1


_records_st = st.lists(
    st.tuples(st.datetimes(), st.sampled_from(_KINDS), _record_payloads()),
    min_size=0,  # include the empty list — the empty branch must honor width too
    max_size=4,
)


@given(
    zoom=st.sampled_from([Zoom.SUMMARY, Zoom.DETAILED, Zoom.FULL]),
    kind=st.sampled_from(_KINDS),
    payload=_record_payloads(),
    width=st.integers(min_value=20, max_value=80),
    ts=st.datetimes(),
    attn=st.sampled_from([None, _attn_low, _attn_mid, _attn_high]),
    gutter=st.sampled_from([None, gutter_lifecycle]),
)
def test_record_line_composed_honors_width(zoom, kind, payload, width, ts, attn, gutter) -> None:
    b = record_line_composed(ts, kind, payload, zoom, width, gutter_fn=gutter, attention_fn=attn)
    assert b.width == width


@given(
    zoom=st.sampled_from([Zoom.MINIMAL, Zoom.SUMMARY, Zoom.DETAILED, Zoom.FULL]),
    records=_records_st,
    width=st.integers(min_value=20, max_value=80),
)
def test_record_timeline_honors_width(zoom, records, width) -> None:
    assert record_timeline(records, zoom, width).width == width


@given(
    zoom=st.sampled_from([Zoom.MINIMAL, Zoom.SUMMARY, Zoom.DETAILED, Zoom.FULL]),
    records=_records_st,
    width=st.integers(min_value=20, max_value=80),
    attn=st.sampled_from([None, _attn_mid]),
    gutter=st.sampled_from([None, gutter_lifecycle]),
)
def test_record_map_honors_width(zoom, records, width, attn, gutter) -> None:
    b = record_map(records, zoom, width, gutter_fn=gutter, attention_fn=attn)
    assert b.width == width
