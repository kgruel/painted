"""Tests for cells.span: Span and Line primitives."""

from painted import Line, Span, Style
from painted.tui import Buffer


class TestStyleMerge:
    """Style.merge precedence — overlay wins on set fields, base attrs survive.

    `base.merge(overlay)`: color fields take overlay when overlay sets them
    (non-None), else keep base; boolean attrs are OR'd, so a base attribute is
    never dropped by an overlay that simply doesn't set it. This is the rule the
    cell.py demo exercised; pinned here directly instead of via a stripped golden.
    """

    def test_overlay_overrides_color_attrs_applied_base_bold_survives(self):
        base = Style(fg="blue", bold=True)
        overlay = Style(fg="red", italic=True)
        merged = base.merge(overlay)
        assert merged.fg == "red"  # overlay color wins
        assert merged.italic  # overlay attribute applied
        assert merged.bold  # base attribute retained (OR semantics)
        assert merged.bg is None  # neither set bg

    def test_overlay_unset_color_keeps_base(self):
        merged = Style(fg="green").merge(Style(bold=True))
        assert merged.fg == "green"  # overlay left fg=None -> base kept
        assert merged.bold


class TestSpanWidth:
    def test_ascii(self):
        assert Span("hello").width == 5

    def test_empty(self):
        assert Span("").width == 0

    def test_wide_chars(self):
        # CJK characters are 2 columns wide
        assert Span("\u4e16\u754c").width == 4  # "世界"

    def test_mixed_ascii_and_wide(self):
        assert Span("A\u4e16B").width == 4  # 1 + 2 + 1


class TestLineWidth:
    def test_empty(self):
        assert Line().width == 0

    def test_single_span(self):
        line = Line(spans=(Span("hello"),))
        assert line.width == 5

    def test_multiple_spans(self):
        line = Line(spans=(Span("ab"), Span("cde")))
        assert line.width == 5

    def test_wide_chars(self):
        line = Line(spans=(Span("A"), Span("\u4e16\u754c")))
        assert line.width == 5  # 1 + 4


class TestLineTruncate:
    def test_no_truncation_needed(self):
        line = Line(spans=(Span("abc"),))
        result = line.truncate(10)
        assert result.width == 3

    def test_truncate_single_span(self):
        line = Line(spans=(Span("hello"),))
        result = line.truncate(3)
        assert result.width == 3
        assert result.spans[0].text == "hel"

    def test_truncate_across_spans(self):
        line = Line(spans=(Span("ab"), Span("cde")))
        result = line.truncate(4)
        assert result.width == 4
        assert len(result.spans) == 2
        assert result.spans[0].text == "ab"
        assert result.spans[1].text == "cd"

    def test_truncate_preserves_style(self):
        base = Style(fg="red")
        span_style = Style(bold=True)
        line = Line(spans=(Span("hello", span_style),), style=base)
        result = line.truncate(3)
        assert result.style == base
        assert result.spans[0].style == span_style

    def test_truncate_wide_char_boundary(self):
        # Wide char at boundary shouldn't be included if it doesn't fit
        line = Line(spans=(Span("A\u4e16B"),))  # widths: 1, 2, 1 = 4
        result = line.truncate(2)
        # Only 'A' fits (width 1), '\u4e16' needs 2 more but budget is only 1
        assert result.width == 1
        assert result.spans[0].text == "A"

    def test_truncate_to_zero(self):
        line = Line(spans=(Span("hello"),))
        result = line.truncate(0)
        assert result.width == 0
        assert result.spans == ()


class TestLinePaint:
    def test_paint_single_span(self):
        buf = Buffer(10, 1)
        view = buf.region(0, 0, 10, 1)
        line = Line(spans=(Span("hi"),))
        line.paint(view, 0, 0)
        assert buf.get(0, 0).char == "h"
        assert buf.get(1, 0).char == "i"
        assert buf.get(2, 0).char == " "  # untouched

    def test_paint_with_offset(self):
        buf = Buffer(10, 1)
        view = buf.region(0, 0, 10, 1)
        line = Line(spans=(Span("ab"),))
        line.paint(view, 3, 0)
        assert buf.get(2, 0).char == " "
        assert buf.get(3, 0).char == "a"
        assert buf.get(4, 0).char == "b"

    def test_paint_multiple_spans(self):
        buf = Buffer(10, 1)
        view = buf.region(0, 0, 10, 1)
        line = Line(spans=(Span("ab"), Span("cd")))
        line.paint(view, 0, 0)
        assert buf.get(0, 0).char == "a"
        assert buf.get(1, 0).char == "b"
        assert buf.get(2, 0).char == "c"
        assert buf.get(3, 0).char == "d"


class TestStyleInheritance:
    def test_line_style_merges_onto_span(self):
        base = Style(fg="red")
        span_style = Style(bold=True)
        buf = Buffer(10, 1)
        view = buf.region(0, 0, 10, 1)
        line = Line(spans=(Span("x", span_style),), style=base)
        line.paint(view, 0, 0)
        cell = buf.get(0, 0)
        # Merged: fg from base, bold from span
        assert cell.style.fg == "red"
        assert cell.style.bold is True

    def test_span_style_overrides_line_style(self):
        base = Style(fg="red")
        span_style = Style(fg="blue")
        buf = Buffer(10, 1)
        view = buf.region(0, 0, 10, 1)
        line = Line(spans=(Span("x", span_style),), style=base)
        line.paint(view, 0, 0)
        cell = buf.get(0, 0)
        # Span fg overrides line fg
        assert cell.style.fg == "blue"

    def test_default_span_inherits_line_style(self):
        base = Style(fg="green", bold=True)
        buf = Buffer(10, 1)
        view = buf.region(0, 0, 10, 1)
        line = Line(spans=(Span("y"),), style=base)
        line.paint(view, 0, 0)
        cell = buf.get(0, 0)
        assert cell.style.fg == "green"
        assert cell.style.bold is True


class TestLineToBlock:
    def test_basic_conversion(self):
        line = Line(spans=(Span("hi"),))
        block = line.to_block(5)
        assert block.width == 5
        assert block.height == 1
        assert block.row(0)[0].char == "h"
        assert block.row(0)[1].char == "i"

    def test_pads_to_width(self):
        line = Line(spans=(Span("ab"),))
        block = line.to_block(5)
        assert block.width == 5
        # Cells beyond line content are empty
        assert block.row(0)[2].char == " "
        assert block.row(0)[3].char == " "
        assert block.row(0)[4].char == " "

    def test_truncates_to_width(self):
        line = Line(spans=(Span("hello world"),))
        block = line.to_block(5)
        assert block.width == 5
        assert block.row(0)[4].char == "o"  # "hello"

    def test_preserves_span_style(self):
        style = Style(fg="red", bold=True)
        line = Line(spans=(Span("x", style),))
        block = line.to_block(3)
        cell = block.row(0)[0]
        assert cell.style.fg == "red"
        assert cell.style.bold is True

    def test_merges_line_style(self):
        line_style = Style(fg="blue")
        span_style = Style(bold=True)
        line = Line(spans=(Span("x", span_style),), style=line_style)
        block = line.to_block(3)
        cell = block.row(0)[0]
        # Line style merged with span style
        assert cell.style.fg == "blue"
        assert cell.style.bold is True

    def test_multiple_spans(self):
        line = Line(
            spans=(
                Span("ab", Style(fg="red")),
                Span("cd", Style(fg="blue")),
            )
        )
        block = line.to_block(6)
        assert block.row(0)[0].char == "a"
        assert block.row(0)[0].style.fg == "red"
        assert block.row(0)[2].char == "c"
        assert block.row(0)[2].style.fg == "blue"

    def test_empty_line(self):
        line = Line()
        block = line.to_block(3)
        assert block.width == 3
        assert block.height == 1
        # All empty cells
        assert block.row(0)[0].char == " "

    def test_wide_char_expands_with_placeholder(self):
        line = Line(spans=(Span("\u4e16"),))  # "世" (2 columns)
        block = line.to_block(2)
        assert block.row(0)[0].char == "\u4e16"
        assert block.row(0)[1].char == " "

    def test_wide_char_dropped_if_width_too_small(self):
        line = Line(spans=(Span("\u4e16"),))
        block = line.to_block(1)
        assert block.row(0)[0].char == " "


class TestLineWrap:
    """Line.wrap — multi-line reflow of multi-style text (the rung above to_block)."""

    def _chars(self, block, row):
        return [c.char for c in block.row(row)]

    def test_word_wrap_basic(self):
        line = Line(spans=(Span("hello world"),))
        block = line.wrap(6)  # WORD is the default
        assert block.width == 6
        assert block.height == 2
        assert "".join(self._chars(block, 0)).rstrip() == "hello"
        assert "".join(self._chars(block, 1)).rstrip() == "world"

    def test_default_mode_is_word(self):
        from painted import Wrap

        line = Line(spans=(Span("hello world"),))
        a, b = line.wrap(6), line.wrap(6, wrap=Wrap.WORD)
        assert [a.row(i) for i in range(a.height)] == [b.row(i) for i in range(b.height)]

    def test_style_rides_across_wrap_boundary(self):
        # A bold word and a plain word wrap to separate rows; each keeps its style.
        line = Line(spans=(Span("aaa", Style(bold=True)), Span(" bbb")))
        block = line.wrap(3)
        assert block.height == 2
        assert all(c.char == "a" or c.char == " " for c in block.row(0))
        assert block.row(0)[0].style.bold is True
        assert block.row(1)[0].char == "b"
        assert block.row(1)[0].style.bold is False

    def test_word_straddling_style_boundary(self):
        # Mixed styles inside one whitespace-delimited word survive char-wrapping.
        from painted import Wrap

        line = Line(spans=(Span("ab", Style(fg="red")), Span("cd", Style(fg="blue"))))
        block = line.wrap(2, wrap=Wrap.CHAR)
        assert block.height == 2
        assert block.row(0)[0].style.fg == "red"
        assert block.row(1)[0].char == "c"
        assert block.row(1)[0].style.fg == "blue"

    def test_char_wrap(self):
        from painted import Wrap

        line = Line(spans=(Span("abcdef"),))
        block = line.wrap(3, wrap=Wrap.CHAR)
        assert block.width == 3
        assert block.height == 2
        assert "".join(self._chars(block, 0)) == "abc"
        assert "".join(self._chars(block, 1)) == "def"

    def test_pad_inherits_line_style(self):
        line = Line(spans=(Span("hi", Style(fg="red")),), style=Style(bg="navy"))
        block = line.wrap(5, wrap=__import__("painted").Wrap.NONE)
        # Trailing pad cell carries the Line's base style, not the span style.
        assert block.row(0)[4].char == " "
        assert block.row(0)[4].style.bg == "navy"

    def test_ellipsis_truncates(self):
        from painted import Wrap

        line = Line(spans=(Span("hello world"),))
        block = line.wrap(8, wrap=Wrap.ELLIPSIS)
        assert block.width == 8
        assert block.height == 1
        assert "…" in "".join(self._chars(block, 0))

    def test_rows_fit_width(self):
        line = Line(spans=(Span("the quick", Style(bold=True)), Span(" brown fox jumps")))
        for w in (3, 5, 7, 12):
            block = line.wrap(w)
            assert all(len(block.row(i)) == w for i in range(block.height))

    def test_empty_line(self):
        block = Line().wrap(4)
        assert block.width == 4
        assert block.height == 1

    def test_zero_width(self):
        block = Line(spans=(Span("hi"),)).wrap(0)
        assert block.width == 0


class TestSpanRef:
    """Span.ref — the denotation channel at the text-primitive rung.

    A span's ref rides its characters through every Line sink exactly as its
    style does: ``to_block`` stamps it per cell (a wide glyph's placeholder
    included), ``wrap`` keeps it on every fragment across line breaks,
    ``truncate`` keeps it on the cut span, and ``paint`` writes it through the
    BufferView — where a ref-less span overwrites, the cell un-links.
    """

    def test_to_block_stamps_ref_on_span_cells_only(self):
        line = Line(spans=(Span("a "), Span("link", ref="doc:x"), Span(" b")))
        block = line.to_block(10)
        assert block.cell_ref(0, 0) is None
        assert [block.cell_ref(x, 0) for x in range(2, 6)] == ["doc:x"] * 4
        assert block.cell_ref(6, 0) is None
        assert block.cell_ref(9, 0) is None  # pad cells denote nothing

    def test_to_block_wide_char_placeholder_carries_ref(self):
        line = Line(spans=(Span("你", ref="doc:x"),))
        block = line.to_block(4)
        assert block.cell_ref(0, 0) == "doc:x"
        assert block.cell_ref(1, 0) == "doc:x"  # the placeholder cell
        assert block.cell_ref(2, 0) is None

    def test_to_block_without_refs_allocates_no_grid(self):
        block = Line(spans=(Span("plain"),)).to_block(5)
        assert block._refs is None

    def test_wrap_keeps_ref_on_every_fragment(self):
        # The linked span reflows across two rows; both fragments stay linked.
        line = Line(spans=(Span("go "), Span("linked words", ref="doc:x")))
        block = line.wrap(8)
        assert block.height == 3
        assert block.cell_ref(0, 0) is None  # "go"
        assert block.cell_ref(0, 1) == "doc:x"  # "linked"
        assert block.cell_ref(0, 2) == "doc:x"  # "words"
        assert block.cell_ref(7, 1) is None  # pad cells denote nothing

    def test_wrap_without_refs_allocates_no_grid(self):
        block = Line(spans=(Span("hello world"),)).wrap(5)
        assert block._refs is None

    def test_wrap_ellipsis_marker_denotes_nothing(self):
        from painted import Wrap

        line = Line(spans=(Span("linked text", ref="doc:x"),))
        block = line.wrap(6, wrap=Wrap.ELLIPSIS)
        assert block.height == 1
        assert block.cell_ref(0, 0) == "doc:x"
        # The marker is loss evidence, not content: its cell carries no ref.
        assert block.cell_ref(5, 0) is None

    def test_truncate_keeps_ref_on_cut_span(self):
        line = Line(spans=(Span("abcdef", ref="doc:x"),))
        cut = line.truncate(3)
        assert cut.spans[0].text == "abc"
        assert cut.spans[0].ref == "doc:x"

    def test_paint_stamps_and_clears(self):
        buf = Buffer(6, 1)
        view = buf.region(0, 0, 6, 1)
        Line(spans=(Span("ab", ref="doc:x"),)).paint(view, 0, 0)
        assert buf.hit(0, 0) == "doc:x"
        assert buf.hit(1, 0) == "doc:x"
        assert buf.hit(2, 0) is None
        Line(spans=(Span("cd"),)).paint(view, 0, 0)
        assert buf.hit(0, 0) is None  # a ref-less write un-links


class TestLineToBlockNaturalWidth:
    """width=None sizes naturally — the width contract's 'absent is natural'
    applied to Line.to_block (previously a crash; consumer-hit in loops)."""

    def test_none_width_takes_line_display_width(self):
        line = Line(spans=(Span("hello"),))
        block = line.to_block(None)
        assert block.width == 5
        assert block.height == 1
        assert [c.char for c in block.row(0)] == list("hello")

    def test_none_width_counts_wide_chars(self):
        line = Line(spans=(Span("世"),))  # "世" (2 columns)
        block = line.to_block(None)
        assert block.width == 2
        assert block.row(0)[0].char == "世"
        assert block.row(0)[1].char == " "  # placeholder cell

    def test_none_width_multiple_spans(self):
        line = Line(spans=(Span("ab", Style(fg="red")), Span("cd", Style(fg="blue"))))
        block = line.to_block(None)
        assert block.width == 4
        assert block.row(0)[0].style.fg == "red"
        assert block.row(0)[2].style.fg == "blue"

    def test_none_width_empty_line_is_zero_width(self):
        block = Line().to_block(None)
        assert block.width == 0
        assert block.height == 1

    def test_none_width_preserves_refs(self):
        line = Line(spans=(Span("ab", ref="fact:01X"),))
        block = line.to_block(None)
        assert block.cell_ref(0, 0) == "fact:01X"
        assert block.cell_ref(1, 0) == "fact:01X"


class TestLineNewlines:
    """A newline inside a span is declared line structure — the styled sibling
    of Block.text's split (decision practice/block-text-honors-newlines)."""

    def test_wrap_splits_on_newline(self):
        line = Line(spans=(Span("aa bb\ncc", Style()),))
        block = line.wrap(3)
        assert block.height == 3  # "aa" / "bb" (word-wrapped) / "cc"
        assert [c.char for c in block.row(2)] == ["c", "c", " "]

    def test_wrap_ref_survives_on_both_sides_of_the_break(self):
        line = Line(spans=(Span("ab\ncd", Style(), ref="fact:01X"),))
        block = line.wrap(2)
        assert block.height == 2
        assert block.cell_ref(0, 0) == "fact:01X"
        assert block.cell_ref(0, 1) == "fact:01X"

    def test_to_block_natural_width_is_widest_segment(self):
        line = Line(spans=(Span("a\nbbb", Style()),))
        block = line.to_block(None)
        assert block.height == 2
        assert block.width == 3

    def test_to_block_given_width_clips_each_segment(self):
        line = Line(spans=(Span("hello\nhi", Style()),))
        block = line.to_block(3)
        assert block.height == 2
        assert [c.char for c in block.row(0)] == ["h", "e", "l"]
        assert [c.char for c in block.row(1)] == ["h", "i", " "]

    def test_crlf_is_one_break_no_phantom_column(self):
        line = Line(spans=(Span("a\r\nb", Style()),))
        block = line.to_block(None)
        assert block.height == 2
        assert block.width == 1

    def test_break_between_spans_keeps_styles(self):
        red = Style(fg="red")
        line = Line(spans=(Span("a\n", Style()), Span("b", red)))
        block = line.to_block(None)
        assert block.height == 2
        assert block.row(1)[0].style == red

    def test_all_blank_segments_keep_their_rows_at_natural_width(self):
        block = Line(spans=(Span("\n", Style()),)).to_block(None)
        assert block.height == 2
        assert block.width == 0
