"""Extended coverage tests for painted.block."""

from __future__ import annotations

import pytest

from painted import Block, Style, Wrap
from painted.core._text_width import display_width
from painted.core.block import _char_wrap, _word_wrap, _take_word_prefix, _cells_from_text
from painted.core.buffer import Buffer
from painted.core.cell import Cell
from painted.core.errors import ContractError


S = Style()
S_RED = Style(fg="red")


def _chars(block: Block, y: int = 0) -> list[str]:
    return [c.char for c in block.row(y)]


# --- Block.__init__ validation ---


class TestBlockInitValidation:
    def test_row_width_mismatch_raises(self):
        from painted.core.cell import Cell

        with pytest.raises(ContractError, match="row 0 width 2 != block width 3"):
            Block([[Cell("a", S), Cell("b", S)]], 3)

    def test_refs_height_mismatch_raises(self):
        from painted.core.cell import Cell

        row = [Cell("a", S)]
        with pytest.raises(ContractError, match="refs height 2 != block height 1"):
            Block([row], 1, refs=[[None], [None]])

    def test_refs_row_width_mismatch_raises(self):
        from painted.core.cell import Cell

        row = [Cell("a", S), Cell("b", S)]
        with pytest.raises(ContractError, match="refs row 0 width 1 != block width 2"):
            Block([row], 2, refs=[[None]])


# --- Block immutability ---


class TestBlockImmutability:
    def test_setattr_raises_after_frozen(self):
        b = Block.text("hi", S)
        with pytest.raises(AttributeError, match="immutable"):
            b.width = 99

    def test_setattr_raises_for_any_attribute(self):
        b = Block.empty(2, 2)
        with pytest.raises(AttributeError, match="immutable"):
            b.ref = "changed"


# --- Block.text() edge cases ---


class TestBlockTextEdgeCases:
    def test_width_zero_returns_empty(self):
        b = Block.text("hello", S, width=0)
        assert b.width == 0
        assert b.height == 1

    def test_width_negative_returns_empty(self):
        b = Block.text("hello", S, width=-5)
        assert b.width == 0
        assert b.height == 1

    def test_text_with_ref(self):
        b = Block.text("hi", S, ref="label")
        assert b.ref == "label"


# --- Block.text() newlines as declared line structure ---
# (decision practice/block-text-honors-newlines: hard break first, wrap mode
# applies within each segment — never scrubbed to a space)


class TestBlockTextNewlines:
    def test_natural_width_multiline(self):
        b = Block.text("a\nbb", S)
        assert b.height == 2
        assert b.width == 2
        assert _chars(b, 0) == ["a", " "]
        assert _chars(b, 1) == ["b", "b"]

    def test_none_wrap_clips_each_segment(self):
        b = Block.text("hello\nhi", S, width=3)
        assert b.height == 2
        assert _chars(b, 0) == ["h", "e", "l"]
        assert _chars(b, 1) == ["h", "i", " "]

    def test_word_wrap_reflows_each_segment_independently(self):
        b = Block.text("aa bb\ncc", S, width=3, wrap=Wrap.WORD)
        assert b.height == 3
        assert _chars(b, 0) == ["a", "a", " "]
        assert _chars(b, 1) == ["b", "b", " "]
        assert _chars(b, 2) == ["c", "c", " "]

    def test_ellipsis_marks_each_overflowing_segment(self):
        b = Block.text("hello\nhi", S, width=4, wrap=Wrap.ELLIPSIS)
        assert b.height == 2
        assert _chars(b, 0) == ["h", "e", "l", "…"]
        assert _chars(b, 1) == ["h", "i", " ", " "]

    def test_trailing_newline_is_a_blank_row(self):
        b = Block.text("a\n", S, width=2)
        assert b.height == 2
        assert _chars(b, 1) == [" ", " "]

    def test_crlf_is_one_break_no_phantom_column(self):
        b = Block.text("a\r\nb", S)
        assert b.height == 2
        assert b.width == 1

    def test_width_zero_collapses_before_the_split(self):
        b = Block.text("a\nb", S, width=0)
        assert b.width == 0
        assert b.height == 1

    def test_ref_applies_to_whole_block(self):
        b = Block.text("a\nb", S, ref="label")
        assert b.ref == "label"
        assert b.height == 2


# --- Block.text() Wrap.ELLIPSIS ---


class TestBlockTextEllipsis:
    def test_ellipsis_width_1(self):
        b = Block.text("hello", S, width=1, wrap=Wrap.ELLIPSIS)
        assert b.width == 1
        assert _chars(b) == ["…"]

    def test_ellipsis_content_fits(self):
        b = Block.text("hi", S, width=10, wrap=Wrap.ELLIPSIS)
        assert b.width == 10
        assert _chars(b)[:2] == ["h", "i"]

    def test_ellipsis_truncates_long_text(self):
        b = Block.text("abcdef", S, width=4, wrap=Wrap.ELLIPSIS)
        row = _chars(b)
        assert row[-1] == " " or "…" in row
        assert "…" in row

    def test_ellipsis_degrades_to_ascii(self):
        """Wrap.ELLIPSIS reads the ambient marker — '...' under ASCII icons.

        The marker is 3 columns wide, so content is cut to width-3 to make room
        (no assuming a 1-column ellipsis)."""
        from painted.icon_set import ASCII_ICONS, reset_icons, use_icons

        with use_icons(ASCII_ICONS):
            b = Block.text("hello world", S, width=8, wrap=Wrap.ELLIPSIS)
            assert "".join(_chars(b)) == "hello..."
        reset_icons()

    def test_ellipsis_ascii_no_room_for_content(self):
        from painted.icon_set import ASCII_ICONS, reset_icons, use_icons

        with use_icons(ASCII_ICONS):
            b = Block.text("hello", S, width=2, wrap=Wrap.ELLIPSIS)
            # marker (3) wider than budget (2) -> marker alone, clipped
            assert "".join(_chars(b)) == ".."
        reset_icons()


# --- Block.text() Wrap.CHAR ---


class TestBlockTextCharWrap:
    def test_char_wrap_basic(self):
        b = Block.text("abcdef", S, width=3, wrap=Wrap.CHAR)
        assert b.width == 3
        assert b.height == 2
        assert _chars(b, 0) == ["a", "b", "c"]
        assert _chars(b, 1) == ["d", "e", "f"]

    def test_char_wrap_empty_text(self):
        b = Block.text("", S, width=5, wrap=Wrap.CHAR)
        assert b.width == 5
        assert b.height == 1

    def test_char_wrap_with_ref(self):
        b = Block.text("abcd", S, width=2, wrap=Wrap.CHAR, ref="cw")
        assert b.ref == "cw"
        assert b.height == 2


# --- Block.text() Wrap.WORD ---


class TestBlockTextWordWrap:
    def test_word_wrap_basic(self):
        b = Block.text("hello world", S, width=6, wrap=Wrap.WORD)
        assert b.width == 6
        assert b.height == 2
        assert _chars(b, 0)[:5] == ["h", "e", "l", "l", "o"]
        assert _chars(b, 1)[:5] == ["w", "o", "r", "l", "d"]

    def test_word_wrap_long_word_broken(self):
        b = Block.text("abcdefgh", S, width=3, wrap=Wrap.WORD)
        assert b.width == 3
        assert b.height >= 3

    def test_word_wrap_trailing_unrepresentable_char_no_phantom_row(self):
        """A final word that cannot be represented in the budget (a width-2 char
        in a width-1 column) must not leave a phantom blank trailing row.

        Regression: the unified word-wrap engine appended its accumulator
        unconditionally, so a trailing word drained to empty by the
        too-wide-to-place path added an all-blank row — inflating height and
        diverging from the pre-unification ``lines if lines else ['']`` contract
        (and from CHAR wrap, which never had the bug)."""
        b = Block.text("a 中", S, width=1, wrap=Wrap.WORD)
        assert b.width == 1
        assert b.height == 1
        assert _chars(b, 0) == ["a"]


# --- Block.empty() with ref ---


class TestBlockEmptyWithRef:
    def test_empty_with_ref(self):
        b = Block.empty(3, 2, ref="bg")
        assert b.ref == "bg"
        assert b.width == 3
        assert b.height == 2


# --- Block.paint() paths ---


class TestBlockPaint:
    def test_paint_no_ref_no_refs(self):
        """Covers the basic paint path (lines 126-132)."""
        b = Block.text("AB", S)
        buf = Buffer(4, 1)
        b.paint(buf, 0, 0)
        assert buf.get(0, 0).char == "A"
        assert buf.get(1, 0).char == "B"
        assert buf.hit(0, 0) is None

    def test_paint_with_block_ref(self):
        """Covers the paint path using block.ref (lines 134-140)."""
        b = Block.text("XY", S, ref="btn")
        buf = Buffer(4, 1)
        b.paint(buf, 0, 0)
        assert buf.get(0, 0).char == "X"
        assert buf.hit(0, 0) == "btn"
        assert buf.hit(1, 0) == "btn"

    def test_paint_with_per_cell_refs(self):
        """Covers the paint path using per-cell _refs (lines 142-151)."""
        from painted.core.cell import Cell

        row = [Cell("a", S), Cell("b", S)]
        refs = [["left", None]]
        b = Block([row], 2, refs=refs)
        buf = Buffer(4, 1)
        b.paint(buf, 0, 0)
        assert buf.hit(0, 0) == "left"
        assert buf.hit(1, 0) is None

    def test_paint_with_offset(self):
        b = Block.text("Z", S)
        buf = Buffer(5, 5)
        b.paint(buf, 3, 2)
        assert buf.get(3, 2).char == "Z"

    def test_paint_wide_char_into_too_narrow_buffer_does_not_overflow(self):
        b = Block.text("\u4e16", S)
        buf = Buffer(1, 1)
        b.paint(buf, 0, 0)
        rendered = "".join(buf.get(x, 0).char for x in range(buf.width))
        assert display_width(rendered) <= buf.width

    def test_paint_left_clipped_wide_char_does_not_leave_placeholder(self):
        b = Block.text("\u4e16", S_RED)
        buf = Buffer(1, 1)
        b.paint(buf, -1, 0)
        assert buf.get(0, 0) == Cell(" ", S_RED)


# --- Block.row() edge cases ---


class TestBlockRow:
    def test_row_returns_tuple(self):
        b = Block.text("abc", S)
        r = b.row(0)
        assert isinstance(r, tuple)
        assert len(r) == 3

    def test_row_negative_index(self):
        b = Block.text("ab", S, width=2, wrap=Wrap.CHAR)
        # Python tuple supports negative indexing
        r = b.row(-1)
        assert isinstance(r, tuple)

    def test_row_out_of_bounds(self):
        b = Block.text("ab", S)
        with pytest.raises(IndexError):
            b.row(5)


# --- Block.cell_ref() ---


class TestBlockCellRef:
    def test_cell_ref_with_block_ref(self):
        b = Block.text("ab", S, ref="x")
        assert b.cell_ref(0, 0) == "x"
        assert b.cell_ref(1, 0) == "x"

    def test_cell_ref_no_ref(self):
        b = Block.text("ab", S)
        assert b.cell_ref(0, 0) is None

    def test_cell_ref_with_per_cell_refs(self):
        from painted.core.cell import Cell

        row = [Cell("a", S), Cell("b", S)]
        refs = [["alpha", "beta"]]
        b = Block([row], 2, refs=refs)
        assert b.cell_ref(0, 0) == "alpha"
        assert b.cell_ref(1, 0) == "beta"


# --- _cells_from_text internals ---


class TestCellsFromText:
    def test_zero_width_chars_skipped(self):
        # Combining accent (U+0301) is zero-width
        cells = _cells_from_text("a\u0301b", S)
        chars = [c.char for c in cells]
        assert "a" in chars
        assert "b" in chars
        assert "\u0301" not in chars

    def test_wide_char_adds_space_placeholder(self):
        cells = _cells_from_text("世", S)
        assert len(cells) == 2
        assert cells[0].char == "世"
        assert cells[1].char == " "

    def test_max_width_truncation(self):
        cells = _cells_from_text("abcdef", S, max_width=3)
        assert len(cells) == 3


# --- _char_wrap internals ---


class TestCharWrap:
    def test_empty_text_gives_padded_row(self):
        rows = _char_wrap("", 5, S)
        assert len(rows) == 1
        assert len(rows[0]) == 5

    def test_char_wider_than_width_skipped(self):
        # Width=1, but a wide char needs 2 columns
        rows = _char_wrap("世", 1, S)
        assert len(rows) == 1
        # The wide char can't fit; row is padded spaces
        assert all(c.char == " " for c in rows[0])

    def test_exact_width_wraps(self):
        rows = _char_wrap("abcd", 2, S)
        assert len(rows) == 2
        assert rows[0][0].char == "a"
        assert rows[0][1].char == "b"
        assert rows[1][0].char == "c"
        assert rows[1][1].char == "d"


# --- _word_wrap internals ---


class TestWordWrap:
    def test_empty_text(self):
        assert _word_wrap("", 10) == [""]

    def test_zero_width(self):
        assert _word_wrap("hello", 0) == [""]

    def test_single_long_word_broken(self):
        lines = _word_wrap("abcdefgh", 3)
        assert all(len(l) <= 3 for l in lines)
        assert "".join(lines) == "abcdefgh"

    def test_second_word_too_long(self):
        lines = _word_wrap("hi abcdefgh end", 3)
        assert lines[0] == "hi"
        # "abcdefgh" gets broken
        assert all(len(l) <= 3 for l in lines)

    def test_word_wrap_preserves_all_text(self):
        text = "the quick brown fox"
        lines = _word_wrap(text, 10)
        reconstructed = " ".join(lines)
        assert reconstructed == text


# --- _take_word_prefix internals ---


class TestTakeWordPrefix:
    def test_basic_prefix(self):
        prefix, consumed = _take_word_prefix("hello", 3)
        assert prefix == "hel"
        assert consumed == 3

    def test_exact_fit(self):
        prefix, consumed = _take_word_prefix("abc", 3)
        assert prefix == "abc"
        assert consumed == 3

    def test_zero_width_chars_included(self):
        # Combining char after 'a'
        prefix, consumed = _take_word_prefix("a\u0301bc", 2)
        assert "a" in prefix
        assert "\u0301" in prefix

    def test_wide_char_too_big(self):
        # Width=1, wide char needs 2
        prefix, consumed = _take_word_prefix("世abc", 1)
        # Can't fit the wide char; returns empty
        assert prefix == ""
        assert consumed == 0


# --- Block.empty() natural width ---


class TestBlockEmptyNaturalWidth:
    """width=None sizes naturally — empty content has no width. Closes the
    Block.text('', Style()) spacer workaround (consumer-hit twice in loops)."""

    def test_none_width_is_zero_width(self):
        b = Block.empty(None, 2)
        assert b.width == 0
        assert b.height == 2

    def test_none_width_zero_height(self):
        b = Block.empty(None, 0)
        assert b.width == 0
        assert b.height == 0

    def test_spacer_idiom_composes(self):
        from painted import join_vertical

        stack = join_vertical(Block.text("a", S), Block.empty(None, 1), Block.text("b", S))
        assert stack.height == 3
        assert stack.width == 1

    def test_int_width_unchanged(self):
        b = Block.empty(3, 2)
        assert b.width == 3
        assert b.height == 2
        assert b.row(0)[0].char == " "
