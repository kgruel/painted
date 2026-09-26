"""Owner-ratified table boundary: CON-001..007, not iterable shape inference."""

from collections import UserDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, Flag, IntEnum, IntFlag, StrEnum
from types import MappingProxyType
from typing import NamedTuple

import pytest

from painted.core import Block, Line, Span
from painted.core.errors import ContractError
from painted.views import Column, table_lens
from painted.views.lens.shape import transcribe

from tests.helpers import assert_blocks_equal, block_to_text, row_text


ZOOMS = [-1, 0, 1, 2, 3]
BREAKS = ["a\nb", "a\r\nb", "a\rb", "\na", "a\n", "a\n\nb", "\n", "\r\n"]


class Pair(NamedTuple):
    left: object
    right: object


@dataclass
class IterableRecord:
    left: object
    right: object

    def __iter__(self):
        return iter((self.left, self.right))


@dataclass
class EmptyRecord:
    pass


class EmptyTuple(NamedTuple):
    pass


@dataclass
class Suppressed:
    secret: str = field(default="private\nvalue", repr=False)


class Records(Sequence):
    """A declared Sequence, not merely a duck-typed iterable."""

    def __init__(self, rows):
        self.rows = tuple(rows)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        return self.rows[index]


@pytest.mark.parametrize("zoom", ZOOMS)
@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("bad", [42, MappingProxyType({"a": 2}), UserDict(a=2), (2,), None])
def test_unsupported_row_refusal_identifies_index_type_and_remedy(zoom, index, bad):
    rows = [{"a": 1}, {"a": 3}]
    rows.insert(index, bad)
    with pytest.raises(ContractError) as exc:
        table_lens(rows, zoom)
    message = str(exc.value)
    assert f"row {index}" in message
    assert type(bad).__name__ in message
    assert "dict" in message and "dataclass" in message and "NamedTuple" in message


@pytest.mark.parametrize("zoom", ZOOMS)
@pytest.mark.parametrize("factory", [dict, Pair, IterableRecord])
def test_bare_records_are_recognized_before_collection_handling(zoom, factory):
    record = factory(left={"a": 1}, right={"a": 2})
    with pytest.raises(ContractError, match=r"\[record\]"):
        table_lens(record, zoom)
    wrapped = table_lens([record], zoom)
    text = block_to_text(wrapped)
    if zoom <= 0:
        assert text == "1 row x 2 columns\n"
    else:
        assert "left" in text and "right" in text
        assert wrapped.height == 3


@pytest.mark.parametrize("zoom", [0, 1])
@pytest.mark.parametrize(
    "subject", ["", b"", bytearray(), memoryview(b""), set(), frozenset(), MappingProxyType({})]
)
def test_non_record_collections_refuse_even_when_empty(zoom, subject):
    with pytest.raises(ContractError, match="Sequence"):
        table_lens(subject, zoom)


@pytest.mark.parametrize("zoom", ZOOMS)
@pytest.mark.parametrize("record", [{}, EmptyRecord(), EmptyTuple(), Suppressed()])
def test_zero_field_bare_records_are_still_records(zoom, record):
    with pytest.raises(ContractError, match=r"\[record\]"):
        table_lens(record, zoom)


@pytest.mark.parametrize("zoom", [0, 1])
def test_arbitrary_iterable_is_refused_without_iteration(zoom):
    class IterableOnly:
        def __iter__(self):
            pytest.fail("An undeclared iterable must not be consumed")

    with pytest.raises(ContractError, match="Sequence"):
        table_lens(IterableOnly(), zoom)


@pytest.mark.parametrize("zoom", [0, 1])
def test_generator_is_refused_without_consumption(zoom):
    consumed = []

    def records():
        consumed.append(True)
        yield {"a": 1}

    subject = records()
    with pytest.raises(ContractError, match="Sequence"):
        table_lens(subject, zoom)
    assert not consumed


@pytest.mark.parametrize("zoom", ZOOMS)
@pytest.mark.parametrize("factory", [list, tuple, Records])
def test_declared_sequences_retain_supported_heterogeneous_records(zoom, factory):
    rows = [Pair("a", 1), IterableRecord("b", 2), {"right": 3}, {}, Suppressed()]
    assert_blocks_equal(table_lens(factory(rows), zoom), table_lens(rows, zoom))


@pytest.mark.parametrize("zoom", ZOOMS)
@pytest.mark.parametrize("width", [None, 1, 40])
@pytest.mark.parametrize("text", BREAKS)
@pytest.mark.parametrize("location", ["cell", "derived header", "explicit header"])
def test_multiline_input_is_refused_before_disclosure_or_clipping(zoom, width, text, location):
    rows = [{"value": text if location == "cell" else "ok"}]
    columns = None
    if location == "derived header":
        rows = [{text: "ok"}]
    elif location == "explicit header":
        # A break may cross span boundaries; inspect the declared header text.
        columns = [Column(Line((Span(text[:1]), Span(text[1:]))))]
    with pytest.raises(ContractError) as exc:
        table_lens(rows, zoom, width, columns=columns)
    message = str(exc.value)
    assert "single-line" in message and "multiline layout" in message
    if location == "cell":
        assert "row 0" in message and "value" in message
    else:
        assert "header" in message and "column 0" in message


def test_formatted_value_not_just_string_input_is_validated():
    class Multiline:
        def __str__(self):
            return "first\nlast"

    with pytest.raises(ContractError, match="row 0"):
        table_lens([{"value": Multiline()}], 1)


def test_explicit_header_does_not_hide_invalid_derived_header():
    with pytest.raises(ContractError, match="derived header"):
        table_lens([{"first\nlast": 1}], 1, columns=[Column(Line.plain("custom"))])


@pytest.mark.parametrize("zoom", [1, 2, 3])
@pytest.mark.parametrize("width", [None, 8, 40])
def test_static_table_has_no_invented_selection_in_cells_separators_or_padding(zoom, width):
    rows = [{"a": "same", "b": 2}] * 2
    block = table_lens(rows, zoom, width)
    assert block.row(2) == block.row(3)
    assert all(not cell.style.reverse for y in (2, 3) for cell in block.row(y))


@pytest.mark.parametrize("zoom", ZOOMS)
@pytest.mark.parametrize("width", [None, 1, 40])
@pytest.mark.parametrize(
    "rows",
    [
        [{}, {}],
        [EmptyRecord()],
        [EmptyTuple()],
        [Suppressed()],
        [{}, EmptyRecord(), EmptyTuple(), Suppressed()],
    ],
)
def test_zero_visible_fields_are_truthful_counts_at_every_zoom(zoom, width, rows):
    count = len(rows)
    text = f"{count} row{'s' if count != 1 else ''} x 0 columns"
    assert_blocks_equal(table_lens(rows, zoom, width), Block.text(text, width=width))


@pytest.mark.parametrize("zoom", ZOOMS)
def test_zero_field_rows_mixed_with_populated_records_keep_their_rows(zoom):
    rows = [{}, EmptyRecord(), EmptyTuple(), Suppressed(), {"a": "ok"}]
    block = table_lens(rows, zoom)
    if zoom <= 0:
        assert block_to_text(block) == "5 rows x 1 column\n"
    else:
        assert block.height == 7
        assert all(not row_text(block, y).strip() for y in range(2, 6))
        assert block_to_text(block).splitlines()[-1].strip() == "ok"
    assert "private" not in block_to_text(block)


class Level(IntEnum):
    WARN = 2


class Status(StrEnum):
    OK = "ok"


class Color(Enum):
    RED = "red"


class Perm(Flag):
    R = 1
    W = 2


class Bits(IntFlag):
    R = 1
    W = 2


@pytest.mark.parametrize(
    "value, spelling",
    [
        (Level.WARN, "Level.WARN"),
        (Status.OK, "Status.OK"),
        (Color.RED, "Color.RED"),
        (Perm.R, "Perm.R"),
        (Perm.R | Perm.W, "Perm.R|W"),
        (Perm(0), "Perm(0)"),
        (Bits.R | Bits.W, "Bits.R|W"),
        (Bits(0), "0"),
        (Bits(4), "4"),
    ],
)
def test_enum_leaf_spelling_matches_transcription_without_changing_its_zoom_behavior(
    value, spelling
):
    for zoom in ZOOMS:
        assert block_to_text(transcribe(value, zoom, None)) == spelling + "\n"
    for zoom in (1, 2, 3):
        block = table_lens([{"value": value}], zoom)
        assert block_to_text(block).splitlines()[2].strip() == spelling


@pytest.mark.parametrize("zoom", ZOOMS)
@pytest.mark.parametrize(
    "rows, count", [([], 0), ([{}], 0), ([{"a": 1}], 1), ([{"a": 1}, {"b": 2}], 2)]
)
def test_column_override_cardinality_is_validated_at_every_zoom(zoom, rows, count):
    matching = [Column(Line.plain(f"custom {i}")) for i in range(count)]
    table_lens(rows, zoom, columns=matching)
    for wrong in (count + 1, count - 1):
        if wrong < 0:
            continue
        with pytest.raises(ContractError, match="explicit list must match the derived order"):
            table_lens(rows, zoom, columns=[Column(Line.plain("custom"))] * wrong)


@pytest.mark.parametrize("zoom", ZOOMS)
@pytest.mark.parametrize("width", [0, -1])
@pytest.mark.parametrize(
    "subject", [object(), [{"a": "bad\ncell"}], [], [{"bad\nheader": 1}], [42]]
)
def test_nonpositive_width_collapse_precedes_all_validation(zoom, width, subject):
    block = table_lens(subject, zoom, width, columns=[Column(Line.plain("bad\nheader"))])
    assert_blocks_equal(block, Block.empty(0, 1))
