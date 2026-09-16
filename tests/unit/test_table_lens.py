"""Unit tier — table_lens: the lens rung of table().

The behaviors here are the ones the consumer review (2026-09-15) asked for and
the ones the refusals protect. `table()` stays the stateful component; this
pins that its lens projection derives columns from *declared* fields only, and
refuses the two shapes transcription already covers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import pytest

from painted.core.block import Block
from painted.core.compose import Align
from painted.core.errors import ContractError
from painted.core.span import Line
from painted.views import table_lens
from painted.views.components._table import Column

ROWS = [
    {"service": "api-gateway", "status": "ok", "pct": 99},
    {"service": "db", "status": "warn", "pct": 71},
]


def rows_of(block: Block) -> list[str]:
    return ["".join(c.char for c in block.row(y)).rstrip() for y in range(block.height)]


def test_dicts_become_columns_in_first_seen_order():
    out = rows_of(table_lens(ROWS, 1))
    assert out[0].split("│") == ["service    ", "status", "pct"]
    assert "api-gateway" in out[2]
    assert "db" in out[3]


def test_header_row_then_rule_then_one_row_per_record():
    block = table_lens(ROWS, 1)
    assert block.height == 2 + len(ROWS)  # header + rule + rows


def test_dataclass_fields_become_columns():
    @dataclass
    class Host:
        name: str
        cores: int

    out = rows_of(table_lens([Host("a", 8), Host("b", 16)], 1))
    assert out[0].split("│") == ["name", "cores"]


def test_namedtuple_fields_become_columns():
    class Point(NamedTuple):
        x: int
        y: int

    out = rows_of(table_lens([Point(1, 2)], 1))
    assert out[0].split("│") == ["x", "y"]


def test_missing_key_renders_an_empty_cell_not_a_shifted_row():
    """A row that omits a field did not declare it — the column stays aligned."""
    out = rows_of(table_lens([{"a": 1}, {"b": 2}], 1))
    assert out[0].split("│") == ["a", "b"]
    assert out[2] == "1\u2502"  # 'a' filled, 'b' blank (separator survives rstrip)
    assert out[3] == " \u25022"  # 'a' blank, 'b' filled


def test_numeric_column_aligns_right_and_text_column_left():
    """Alignment is derived from the declared type, not guessed."""
    out = rows_of(table_lens([{"n": 1}, {"n": 100}], 1))
    assert out[2].endswith("1") and out[2].startswith(" ")
    assert out[3] == "100"


def test_bool_is_not_numeric_for_alignment():
    """bool is an int subclass; excluded here as it is in `_is_numeric_sequence`."""
    out = rows_of(table_lens([{"flag": True}, {"flag": False}], 1))
    assert out[2] == "True"  # left-aligned


@pytest.mark.parametrize("zoom", [0, -1])
def test_zoom_zero_is_the_count_line(zoom: int):
    assert rows_of(table_lens(ROWS, zoom)) == ["2 rows x 3 columns"]


def test_zoom_zero_singular_row_and_column():
    assert rows_of(table_lens([{"a": 1}], 0)) == ["1 row x 1 column"]


def test_empty_sequence_is_zero_rows_at_any_zoom():
    assert rows_of(table_lens([], 1)) == ["0 rows"]


@pytest.mark.parametrize("width", [1, 6, 12, 24, 80])
def test_width_is_exact(width: int):
    """Law 5 — every sibling lens is width-exact; table() alone treats it as a budget."""
    assert table_lens(ROWS, 1, width).width == width


def test_natural_width_is_content_width():
    assert table_lens(ROWS, 1).width == table_lens(ROWS, 1, None).width


def test_explicit_columns_override_derivation():
    cols = [
        Column(header=Line.plain("SVC"), width=5),
        Column(header=Line.plain("ST"), width=4),
        Column(header=Line.plain("%"), width=3, align=Align.END),
    ]
    out = rows_of(table_lens(ROWS, 1, columns=cols))
    assert out[0].split("│") == ["SVC  ", "ST  ", "  %"]


def test_explicit_columns_must_match_the_derived_count():
    with pytest.raises(ContractError, match="must match the derived order"):
        table_lens(ROWS, 1, columns=[Column(header=Line.plain("only"))])


@pytest.mark.parametrize(
    "subject, because",
    [
        ("hello", "a str is not a sequence of records"),
        (5, "an int is not iterable"),
        ({"a": 1}, "a single mapping is paint()'s key/value case"),
        ([1, 2, 3], "scalars declare order, not columns"),
        (["a", "b"], "strings declare no field schema"),
    ],
)
def test_refuses_shapes_that_declare_no_columns(subject, because: str):
    """Refusal over coercion: a table is a claim about named fields."""
    with pytest.raises(ContractError):
        table_lens(subject, 1)


def test_refusal_message_points_at_paint_for_a_bare_mapping():
    with pytest.raises(ContractError, match="paint"):
        table_lens({"a": 1}, 1)


def test_is_a_projection_onto_table_not_a_second_renderer():
    """The lens output equals driving table() by hand — same component, less setup."""
    from painted.views.components._table import AUTO, TableState, table

    cols = [
        Column(header=Line.plain("service"), width=AUTO, ellipsis=True),
        Column(header=Line.plain("status"), width=AUTO, ellipsis=True),
        Column(header=Line.plain("pct"), width=AUTO, align=Align.END, ellipsis=True),
    ]
    data = [[Line.plain(str(r[k])) for k in ("service", "status", "pct")] for r in ROWS]
    expected = table(TableState().with_count(len(data)), cols, data, visible_height=len(data))
    assert rows_of(table_lens(ROWS, 1)) == rows_of(expected)
