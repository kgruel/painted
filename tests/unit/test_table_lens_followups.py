"""Consumer N-1..N-3: text-boundary parity, declared alignment, honest guidance."""

from dataclasses import dataclass, field, replace
from enum import IntEnum, IntFlag

import pytest

from painted.core import Align, Block, Line, Span, Style
from painted.core.compose import fit_to_width
from painted.core.errors import ContractError
from painted.views import AUTO, Column, EllipsisSide, Fill, TableState, table, table_lens
from painted.views.lens.shape import transcribe

from tests.helpers import assert_blocks_equal, row_text


# Enumerate the entire small domain: no C0/C1 separator may silently disappear.
CONTROLS = [chr(i) for i in (*range(0x20), *range(0x7F, 0xA0)) if i not in (10, 13)]
WIDTHS = [None, 2, 5, 20]


class Formatted:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return self.text


@pytest.mark.parametrize("control", CONTROLS, ids=lambda c: f"U+{ord(c):04X}")
@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("location", ["cell", "derived header"])
def test_nonbreak_controls_keep_a_space_in_formatted_cells_and_headers(control, width, location):
    text = f"a{control}b"
    if location == "cell":
        rows, expected = [{"v": Formatted(text)}], [{"v": "a b"}]
    else:
        # Non-string keys keep identity; only their display spelling is scrubbed.
        rows, expected = [{Formatted(text): "ok"}], [{"a b": "ok"}]
    block = table_lens(rows, 1, width)
    assert_blocks_equal(block, table_lens(expected, 1, width))
    if width is None:
        y = 2 if location == "cell" else 0
        assert row_text(block, y) == "a b"
        assert row_text(block, y) == row_text(transcribe(text, 1, None), 0)


@pytest.mark.parametrize("control", CONTROLS, ids=lambda c: f"U+{ord(c):04X}")
@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"width": 12, "align": Align.END},
        {"width": Fill(2), "min_width": 4, "max_width": 9, "align": Align.CENTER},
        {"width": 4, "ellipsis": True, "ellipsis_side": EllipsisSide.START},
    ],
)
def test_explicit_styled_headers_keep_spaces_styles_refs_settings_and_caller_values(
    control, width, settings
):
    spans = (
        Span(f"a{control}b", Style(fg="red", bg="blue", italic=True), ref="header:first"),
        Span(f"c{control}d", Style(underline=True, bg="blue", italic=True), ref="header:second"),
    )
    header = Line(spans, style=Style(bg="blue", italic=True))
    column = Column(header, **settings)
    columns = [column]
    rows = [{"v": "x"}]
    clean_header = replace(
        header, spans=(replace(spans[0], text="a b"), replace(spans[1], text="c d"))
    )
    block = table_lens(rows, 1, width, columns=columns)
    expected = table_lens(rows, 1, width, columns=[replace(column, header=clean_header)])
    assert_blocks_equal(block, expected)
    assert [[block.cell_ref(x, y) for x in range(block.width)] for y in range(block.height)] == [
        [expected.cell_ref(x, y) for x in range(expected.width)] for y in range(expected.height)
    ]
    if width is None and not settings:
        assert row_text(block, 0) == "a bc d"
        assert block.row(0)[1].style.fg == "red"
        assert block.row(0)[4].style.underline
        assert all(cell.style.bg == "blue" and cell.style.italic for cell in block.row(0))
    assert columns == [column] and columns[0] is column
    assert column.header is header and header.spans == spans
    assert tuple(span.text for span in spans) == (f"a{control}b", f"c{control}d")
    assert rows == [{"v": "x"}]


def test_styled_ref_header_is_preserved_at_the_table_projection_boundary(monkeypatch):
    # table() currently drops its buffer's ref lane on extraction and overrides
    # Line.style. Pin what the lens passes it without widening this fix into table().
    from importlib import import_module

    module = import_module("painted.views.lens.table")
    first_style = Style(fg="red", bg="blue", bold=True, dim=True, underline=True, reverse=True)
    second_style = Style(fg="green", italic=True)
    spans = (
        Span("a\tb", first_style, ref="first"),
        Span("c\x85d", second_style, ref="second"),
    )
    header = Line(spans, style=Style(italic=True))
    column = Column(header)
    columns = [column]
    rows = [{"v": "ok"}]
    expected = Line(
        (Span("a b", first_style, ref="first"), Span("c d", second_style, ref="second")),
        style=Style(italic=True),
    ).to_block(None)
    calls = []

    def render(state, columns, rows, **kwargs):
        forwarded = columns[0].header
        # Assert before materialization: to_block's Cell scrubbing can hide a
        # missing lens sanitizer, and merged cell styles can hide Line.style loss.
        assert [span.text for span in forwarded.spans] == ["a b", "c d"]
        assert [span.style for span in forwarded.spans] == [first_style, second_style]
        assert [span.ref for span in forwarded.spans] == ["first", "second"]
        assert forwarded.style == Style(italic=True)
        materialized = forwarded.to_block(None)
        assert_blocks_equal(materialized, expected)
        assert [materialized.cell_ref(x, 0) for x in range(6)] == ["first"] * 3 + ["second"] * 3
        calls.append(True)
        return table(state, columns, rows, **kwargs)

    monkeypatch.setattr(module, "table", render)
    table_lens(rows, 1, columns=columns)
    assert calls == [True]
    assert columns == [column] and columns[0] is column
    assert column.header is header and header.spans == spans
    assert [span.text for span in spans] == ["a\tb", "c\x85d"]
    assert [span.style for span in spans] == [first_style, second_style]
    assert [span.ref for span in spans] == ["first", "second"]
    assert header.style == Style(italic=True)
    assert rows == [{"v": "ok"}]


@pytest.mark.parametrize("zoom", [-1, 0, 1, 3])
@pytest.mark.parametrize("width", [None, 1, 20])
@pytest.mark.parametrize("location", ["cell", "derived header", "explicit header"])
def test_break_refusal_precedes_scrubbing_count_and_clipping(zoom, width, location):
    rows = [{"v": "a\t\r\nb" if location == "cell" else "ok"}]
    columns = None
    if location == "derived header":
        rows = [{"a\x85\r\nb": "ok"}]
    elif location == "explicit header":
        columns = [Column(Line((Span("a\x00\r"), Span("\n\x7fb"))))]
    with pytest.raises(ContractError, match="single-line"):
        table_lens(rows, zoom, width, columns=columns)


@pytest.mark.parametrize("zoom", [-1, 0])
@pytest.mark.parametrize("width", WIDTHS)
def test_other_controls_are_valid_at_count_zoom(zoom, width):
    text = "a" + "".join(CONTROLS) + "b"
    assert_blocks_equal(
        table_lens([{text: text}], zoom, width, columns=[Column(Line.plain(text))]),
        Block.text("1 row x 1 column", width=width),
    )


@pytest.mark.parametrize("zoom", [-1, 0, 1, 3])
@pytest.mark.parametrize("width", [0, -1])
def test_nonpositive_width_does_not_format_or_validate(zoom, width):
    class MustNotFormat:
        def __str__(self):
            pytest.fail("nonpositive width must collapse first")

    assert_blocks_equal(
        table_lens(
            [{MustNotFormat(): MustNotFormat()}],
            zoom,
            width,
            columns=[Column(Line((Span("\r"), Span("\n"))))],
        ),
        Block.empty(0, 1),
    )


@pytest.mark.parametrize("zoom", [-1, 0, 1, 3])
def test_suppressed_values_are_never_formatted(zoom):
    class MustNotFormat:
        def __str__(self):
            pytest.fail("repr=False is suppression, not text to validate or scrub")

    @dataclass
    class Record:
        visible: str = "a\tb"
        hidden: object = field(default_factory=MustNotFormat, repr=False)

    assert_blocks_equal(table_lens([Record()], zoom), table_lens([{"visible": "a b"}], zoom))


@pytest.mark.parametrize("text", ["界é", "e\u0301", "👩‍💻", "\ue0b0─", "a\u2028b\u2029c"])
@pytest.mark.parametrize("width", WIDTHS)
def test_unicode_noncontrols_keep_the_existing_table_renderer_behavior(text, width):
    header = Line((Span(text, Style(fg="green"), ref="unicode"),), Style(italic=True))
    columns = [Column(header, width=AUTO, ellipsis=True)]
    expected = table(
        TableState().with_count(1),
        columns,
        [[Line.plain(text)]],
        visible_height=1,
        width=width,
        selected_style=Style(),
    )
    if width is not None:
        expected = fit_to_width(expected, width)
    assert_blocks_equal(table_lens([{"v": text}], 1, width, columns=columns), expected)
    assert_blocks_equal(
        table_lens([{text: text}], 1, width),
        table_lens([{"v": text}], 1, width, columns=[Column(Line.plain(text), ellipsis=True)]),
    )


class Level(IntEnum):
    WARN = 2


class Bits(IntFlag):
    R = 1
    W = 2


@pytest.mark.parametrize(
    "value, spelling, numeric",
    [
        (Level.WARN, "Level.WARN", False),
        (Bits.R | Bits.W, "Bits.R|W", False),
        (Bits(4), "4", False),
        (1, "1", True),
        (1.5, "1.5", True),
        (True, "True", False),
    ],
)
@pytest.mark.parametrize("width", [None, 24])
def test_declared_enums_align_left_ordinary_numbers_right_and_overrides_win(
    value, spelling, numeric, width
):
    name = "a long field name"
    block = table_lens([{name: value}], 1, width)
    expected = spelling.rjust(len(name)) if numeric else spelling.ljust(len(name))
    assert row_text(block, 2) == expected.ljust(width or len(name))
    for align in (Align.START, Align.END):
        explicit = table_lens(
            [{name: value}],
            1,
            width,
            columns=[Column(Line.plain(name), width=len(name), align=align)],
        )
        expected = spelling.rjust(len(name)) if align == Align.END else spelling.ljust(len(name))
        assert row_text(explicit, 2) == expected.ljust(width or len(name))


@pytest.mark.parametrize("zoom", [-1, 0, 1, 3])
@pytest.mark.parametrize("rows", [[], [{}]])
def test_empty_column_mismatch_has_no_empty_parentheses(zoom, rows):
    with pytest.raises(ContractError) as exc:
        table_lens(rows, zoom, columns=[Column(Line.plain("custom"))])
    assert str(exc.value) == (
        "table_lens was given 1 columns but the data declares 0; "
        "the explicit list must match the derived order"
    )


@pytest.mark.parametrize(
    "name, displayed",
    [
        ("a\x1bb", r"'a\x1bb'"),
        ("a\nb", r"'a\nb'"),
        ("a\rb", r"'a\rb'"),
        ("a\x00b", r"'a\x00b'"),
        ("a\tb", r"'a\tb'"),
        ("a\x7fb", r"'a\x7fb'"),
        ("a\x85b", r"'a\x85b'"),
        ("a\x9bb", r"'a\x9bb'"),
        ("ordinary", "'ordinary'"),
        ("界é", "'界é'"),
        (42, "'42'"),
        (Formatted("a\x1bb"), r"'a\x1bb'"),
    ],
    ids=["ESC", "LF", "CR", "NUL", "TAB", "DEL", "NEL", "CSI", "plain", "unicode", "int", "object"],
)
@pytest.mark.parametrize("zoom, width", [(1, None), (0, 1)])
def test_column_mismatch_escapes_field_display_before_text_validation(name, displayed, zoom, width):
    class MustNotFormat:
        def __str__(self):
            pytest.fail("column mismatch must precede cell formatting")

    value = MustNotFormat()
    row = {name: value}
    rows = [row]
    # Even invalid explicit headers are diagnosed only after cardinality.
    column = Column(Line.plain("bad\nheader"))
    columns = [column, column]
    with pytest.raises(ContractError) as exc:
        table_lens(rows, zoom, width, columns=columns)
    message = str(exc.value)
    assert message == (
        f"table_lens was given 2 columns but the data declares 1 ({displayed}); "
        "the explicit list must match the derived order"
    )
    assert not any(ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0 for c in message)
    assert rows == [row] and rows[0] is row
    assert len(row) == 1 and next(iter(row)) is name and row[name] is value
    assert columns == [column, column] and all(c is column for c in columns)
    assert column.header.spans[0].text == "bad\nheader"


def test_column_mismatch_keeps_distinct_keys_and_first_seen_union_order():
    key = Formatted("same")
    rows = [{key: "first", 42: "number"}, {"same": "last", key: "again"}]
    original_items = [list(row.items()) for row in rows]
    with pytest.raises(ContractError) as exc:
        table_lens(rows, -1, columns=[])
    assert str(exc.value) == (
        "table_lens was given 0 columns but the data declares 3 ('same', '42', 'same'); "
        "the explicit list must match the derived order"
    )
    assert [list(row.items()) for row in rows] == original_items
    assert next(iter(rows[0])) is key
    # Matching positional overrides still look values up by original key, not text.
    block = table_lens(rows, 1, columns=[Column(Line.plain("x")) for _ in range(3)])
    expected = table_lens(
        [{"a": "first", "b": "number"}, {"c": "last", "a": "again"}],
        1,
        columns=[Column(Line.plain("x")) for _ in range(3)],
    )
    assert_blocks_equal(block, expected)


@pytest.mark.parametrize("width", [0, -1])
def test_nonpositive_width_collapses_before_column_mismatch(width):
    class MustNotFormat:
        def __str__(self):
            pytest.fail("nonpositive width must precede mismatch name formatting")

    assert_blocks_equal(
        table_lens([{MustNotFormat(): "ok"}], 0, width, columns=[]), Block.empty(0, 1)
    )
