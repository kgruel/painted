"""Extended tests for painted.compose — covering ref propagation, alignment, edge cases."""

from painted import (
    Align,
    Block,
    Cell,
    Style,
    border,
    join_horizontal,
    join_responsive,
    join_vertical,
    pad,
    truncate,
    vslice,
)
from painted.core._text_width import char_width
from painted.core.borders import HEAVY, ROUNDED
from tests.helpers import row_text, text_block


def _text_block_with_refs(
    lines: list[str], refs: list[list[str | None]], style: Style = Style()
) -> Block:
    """Build a Block with per-cell ref data (_refs)."""
    width = max(len(ln) for ln in lines) if lines else 0
    rows = []
    for line in lines:
        row = [Cell(ch, style) for ch in line]
        row += [Cell(" ", style)] * (width - len(line))
        rows.append(row)
    return Block(rows, width, refs=refs)


def _row_refs(block: Block, row_idx: int) -> list[str | None]:
    if block._refs is not None:
        return list(block._refs[row_idx])
    return []


# ---------------------------------------------------------------------------
# pad() with ref propagation
# ---------------------------------------------------------------------------


class TestPadRefPropagation:
    def test_pad_preserves_block_ref_when_no_refs(self):
        """pad() should forward block.ref when _refs is None."""
        b = text_block(["ab"], ref="box")
        result = pad(b, left=1, right=1, top=1, bottom=1)
        assert result.ref == "box"
        assert result._refs is None

    def test_pad_propagates_refs_matrix(self):
        """pad() should wrap _refs with None padding cells."""
        b = _text_block_with_refs(["ab"], refs=[["x", "y"]])
        result = pad(b, left=1, right=1, top=1, bottom=1)
        assert result.width == 4
        assert result.height == 3
        # Top row: all None
        assert _row_refs(result, 0) == [None, None, None, None]
        # Content row: None + x + y + None
        assert _row_refs(result, 1) == [None, "x", "y", None]
        # Bottom row: all None
        assert _row_refs(result, 2) == [None, None, None, None]

    def test_pad_refs_left_right_only(self):
        """pad() with only left/right preserves refs correctly."""
        b = _text_block_with_refs(["ab", "cd"], refs=[["a", "b"], ["c", "d"]])
        result = pad(b, left=2, right=1)
        assert result.width == 5
        assert result.height == 2
        assert _row_refs(result, 0) == [None, None, "a", "b", None]
        assert _row_refs(result, 1) == [None, None, "c", "d", None]

    def test_pad_refs_top_bottom_only(self):
        """pad() with only top/bottom adds blank ref rows."""
        b = _text_block_with_refs(["ab"], refs=[["x", "y"]])
        result = pad(b, top=2, bottom=1)
        assert result.height == 4
        assert _row_refs(result, 0) == [None, None]
        assert _row_refs(result, 1) == [None, None]
        assert _row_refs(result, 2) == ["x", "y"]
        assert _row_refs(result, 3) == [None, None]


# ---------------------------------------------------------------------------
# border() with ref propagation
# ---------------------------------------------------------------------------


class TestBorderRefPropagation:
    def test_border_ref_param_used(self):
        """border(ref=...) wraps entire border with that ref."""
        b = text_block(["ab"])
        result = border(b, ref="frame")
        assert result._refs is not None
        # Top border row: all "frame"
        assert _row_refs(result, 0) == ["frame"] * result.width
        # Content row: frame + inner + frame
        refs_row1 = _row_refs(result, 1)
        assert refs_row1[0] == "frame"
        assert refs_row1[-1] == "frame"
        # Bottom border row
        assert _row_refs(result, 2) == ["frame"] * result.width

    def test_border_inherits_block_ref_when_no_refs(self):
        """border() with no ref param inherits block.ref for the border cells."""
        b = text_block(["ab"], ref="inner")
        result = border(b)
        # When block has ref but no _refs, border_ref falls through to block.ref
        assert result._refs is None
        assert result.ref == "inner"

    def test_border_with_block_refs_matrix(self):
        """border() preserves inner _refs and uses border_ref for frame."""
        b = _text_block_with_refs(["ab"], refs=[["x", "y"]])
        result = border(b, ref="fr")
        assert result._refs is not None
        # Top: fr fr fr fr
        assert _row_refs(result, 0) == ["fr", "fr", "fr", "fr"]
        # Content: fr x y fr
        assert _row_refs(result, 1) == ["fr", "x", "y", "fr"]
        # Bottom: fr fr fr fr
        assert _row_refs(result, 2) == ["fr", "fr", "fr", "fr"]

    def test_border_block_refs_no_border_ref(self):
        """border() with block._refs but no ref param uses None for border cells."""
        b = _text_block_with_refs(["ab"], refs=[["x", "y"]])
        result = border(b)
        assert result._refs is not None
        # border_ref is None since no ref param and block._refs is not None
        assert _row_refs(result, 0) == [None, None, None, None]
        assert _row_refs(result, 1) == [None, "x", "y", None]
        assert _row_refs(result, 2) == [None, None, None, None]

    def test_border_block_has_ref_and_refs(self):
        """border() with block that has both .ref and ._refs — _refs takes precedence for inner."""
        b = Block(
            [[Cell("a", Style()), Cell("b", Style())]],
            2,
            ref="fallback",
            refs=[["x", "y"]],
        )
        result = border(b, ref="fr")
        # Inner content uses _refs, not block.ref
        assert _row_refs(result, 1) == ["fr", "x", "y", "fr"]

    def test_border_block_with_ref_no_refs_no_border_ref(self):
        """border() block.ref used for content refs when _refs absent and has_refs true."""
        # has_refs is true because block.ref is set (via another block in join)
        b = text_block(["ab"], ref="inner")
        # Give explicit border ref to trigger has_refs
        result = border(b, ref="bdr")
        assert result._refs is not None
        # Content row: border cells should be "bdr", inner should be "inner"
        assert _row_refs(result, 1) == ["bdr", "inner", "inner", "bdr"]

    def test_border_no_refs_anywhere(self):
        """border() with no refs at all returns block with no _refs."""
        b = text_block(["ab"])
        result = border(b)
        assert result._refs is None
        assert result.ref is None


# ---------------------------------------------------------------------------
# truncate() with ref propagation
# ---------------------------------------------------------------------------


class TestTruncateRefPropagation:
    def test_truncate_no_truncation_returns_same(self):
        """If width >= block width, return same block."""
        b = text_block(["abc"], ref="t")
        result = truncate(b, 5)
        assert result is b

    def test_truncate_preserves_block_ref(self):
        """truncate() forwards block.ref when no _ids."""
        b = text_block(["abcde"], ref="row")
        result = truncate(b, 3)
        assert result.ref == "row"
        assert result._refs is None
        assert result.width == 3

    def test_truncate_with_refs(self):
        """truncate() slices _refs and appends last ref for ellipsis."""
        b = _text_block_with_refs(["abcde"], refs=[["a", "b", "c", "d", "e"]])
        result = truncate(b, 3)
        assert result.width == 3
        assert result._refs is not None
        # width=3: first 2 cells + ellipsis cell, refs: first 2 + ref at index 2
        assert _row_refs(result, 0) == ["a", "b", "c"]

    def test_truncate_width_zero(self):
        """truncate() to width 0 produces empty rows."""
        b = _text_block_with_refs(["abc"], refs=[["x", "y", "z"]])
        result = truncate(b, 0)
        assert result.width == 0
        assert result.height == 1
        assert _row_refs(result, 0) == []

    def test_truncate_ellipsis_degrades_to_ascii(self):
        """truncate(ellipsis=None) reads the ambient marker; '...' under ASCII."""
        from painted.icon_set import ASCII_ICONS, reset_icons, use_icons

        b = text_block(["hello world"])
        assert "".join(c.char for c in truncate(b, 8).row(0)) == "hello w…"
        with use_icons(ASCII_ICONS):
            assert "".join(c.char for c in truncate(b, 8).row(0)) == "hello..."
        reset_icons()

    def test_truncate_width_one(self):
        """truncate() to width 1 produces just the ellipsis."""
        b = _text_block_with_refs(["abc"], refs=[["x", "y", "z"]])
        result = truncate(b, 1)
        assert result.width == 1
        assert row_text(result, 0) == "\u2026"
        assert _row_refs(result, 0) == ["x"]

    def test_truncate_multirow_with_refs(self):
        """truncate() handles multiple rows with _refs."""
        b = _text_block_with_refs(
            ["abcd", "efgh"],
            refs=[["a", "b", "c", "d"], ["e", "f", "g", "h"]],
        )
        result = truncate(b, 3)
        assert result.height == 2
        assert _row_refs(result, 0) == ["a", "b", "c"]
        assert _row_refs(result, 1) == ["e", "f", "g"]

    def test_truncate_preserves_wide_char_placeholder_pairs(self):
        """Truncation must not leave a wide-char lead cell without its placeholder."""
        result = truncate(Block.text("A\u4e16B", Style()), 3)
        row = result.row(0)
        for idx, cell in enumerate(row):
            if char_width(cell.char) == 2:
                assert idx + 1 < len(row)
                assert row[idx + 1].char == " "
                assert row[idx + 1].style == cell.style


# ---------------------------------------------------------------------------
# vslice() with ref propagation
# ---------------------------------------------------------------------------


class TestVsliceRefPropagation:
    def test_vslice_preserves_block_ref(self):
        """vslice() forwards block.ref."""
        b = text_block(["aaa", "bbb", "ccc"], ref="src")
        result = vslice(b, 1, 1)
        assert result.ref == "src"
        assert row_text(result, 0) == "bbb"

    def test_vslice_with_refs(self):
        """vslice() slices _refs rows."""
        b = _text_block_with_refs(
            ["ab", "cd", "ef"],
            refs=[["a1", "a2"], ["b1", "b2"], ["c1", "c2"]],
        )
        result = vslice(b, 1, 2)
        assert result._refs is not None
        assert _row_refs(result, 0) == ["b1", "b2"]
        assert _row_refs(result, 1) == ["c1", "c2"]

    def test_vslice_empty_result_preserves_ref(self):
        """vslice() returning empty block keeps block.ref."""
        b = text_block(["aaa"], ref="kept")
        result = vslice(b, 5, 2)
        assert result.ref == "kept"
        assert result.height == 0

    def test_vslice_zero_height(self):
        """vslice() with height=0 returns empty block."""
        b = text_block(["abc", "def"])
        result = vslice(b, 0, 0)
        assert result.height == 0
        assert result.width == 3


# ---------------------------------------------------------------------------
# join_horizontal() with ref propagation
# ---------------------------------------------------------------------------


class TestJoinHorizontalRefs:
    def test_join_horizontal_empty(self):
        """join_horizontal() with no blocks returns empty."""
        result = join_horizontal()
        assert result.width == 0
        assert result.height == 0

    def test_join_horizontal_with_block_refs(self):
        """join_horizontal() propagates block.ref values."""
        a = text_block(["ab"], ref="left")
        b = text_block(["cd"], ref="right")
        result = join_horizontal(a, b)
        assert result._refs is not None
        assert _row_refs(result, 0) == ["left", "left", "right", "right"]

    def test_join_horizontal_with_refs_matrix(self):
        """join_horizontal() propagates _refs matrices."""
        a = _text_block_with_refs(["ab"], refs=[["a1", "a2"]])
        b = _text_block_with_refs(["cd"], refs=[["b1", "b2"]])
        result = join_horizontal(a, b)
        assert result._refs is not None
        assert _row_refs(result, 0) == ["a1", "a2", "b1", "b2"]

    def test_join_horizontal_mixed_ref_and_no_ref(self):
        """When one block has ref and another has neither, None fills in."""
        a = text_block(["ab"], ref="left")
        b = text_block(["cd"])  # no ref
        result = join_horizontal(a, b)
        assert result._refs is not None
        assert _row_refs(result, 0) == ["left", "left", None, None]

    def test_join_horizontal_gap_with_refs(self):
        """Gap cells get None refs."""
        a = text_block(["a"], ref="L")
        b = text_block(["b"], ref="R")
        result = join_horizontal(a, b, gap=2)
        assert result.width == 4
        assert _row_refs(result, 0) == ["L", None, None, "R"]

    def test_join_horizontal_different_heights_with_refs(self):
        """Taller alignment produces None refs in padding rows."""
        a = text_block(["a", "a"], ref="tall")
        b = text_block(["b"], ref="short")
        result = join_horizontal(a, b, align=Align.START)
        assert result.height == 2
        assert result._refs is not None
        # Row 0: tall block + short block
        assert _row_refs(result, 0) == ["tall", "short"]
        # Row 1: tall block + padding (None)
        assert _row_refs(result, 1) == ["tall", None]

    def test_join_horizontal_align_end(self):
        """END alignment shifts shorter block to bottom."""
        a = text_block(["aa"])
        b = text_block(["bb", "cc"])
        result = join_horizontal(a, b, align=Align.END)
        assert result.height == 2
        # Row 0: 'a' block padded (offset=1), 'b' content
        assert row_text(result, 0) == "  bb"
        # Row 1: 'a' content, 'c' content
        assert row_text(result, 1) == "aacc"

    def test_join_horizontal_align_center(self):
        """CENTER alignment centers shorter blocks."""
        a = text_block(["x"])
        b = text_block(["1", "2", "3"])
        result = join_horizontal(a, b, align=Align.CENTER)
        assert result.height == 3
        # 'x' has height 1, container height 3, offset = (3-1)//2 = 1
        assert row_text(result, 0) == " 1"
        assert row_text(result, 1) == "x2"
        assert row_text(result, 2) == " 3"


# ---------------------------------------------------------------------------
# join_vertical() with ref propagation
# ---------------------------------------------------------------------------


class TestJoinVerticalRefs:
    def test_join_vertical_empty(self):
        """join_vertical() with no blocks returns empty."""
        result = join_vertical()
        assert result.width == 0
        assert result.height == 0

    def test_join_vertical_with_block_refs(self):
        """join_vertical() propagates block.ref values."""
        a = text_block(["ab"], ref="top")
        b = text_block(["cd"], ref="bot")
        result = join_vertical(a, b)
        assert result._refs is not None
        assert _row_refs(result, 0) == ["top", "top"]
        assert _row_refs(result, 1) == ["bot", "bot"]

    def test_join_vertical_with_refs_matrix(self):
        """join_vertical() propagates _refs matrices."""
        a = _text_block_with_refs(["ab"], refs=[["a1", "a2"]])
        b = _text_block_with_refs(["cd"], refs=[["b1", "b2"]])
        result = join_vertical(a, b)
        assert result._refs is not None
        assert _row_refs(result, 0) == ["a1", "a2"]
        assert _row_refs(result, 1) == ["b1", "b2"]

    def test_join_vertical_mixed_ref_and_no_ref(self):
        """When one block has ref and another doesn't, None fills in."""
        a = text_block(["ab"], ref="top")
        b = text_block(["cd"])  # no ref
        result = join_vertical(a, b)
        assert result._refs is not None
        assert _row_refs(result, 0) == ["top", "top"]
        assert _row_refs(result, 1) == [None, None]

    def test_join_vertical_gap_with_refs(self):
        """Gap rows get None refs."""
        a = text_block(["a"], ref="top")
        b = text_block(["b"], ref="bot")
        result = join_vertical(a, b, gap=1)
        assert result.height == 3
        assert _row_refs(result, 0) == ["top"]
        assert _row_refs(result, 1) == [None]
        assert _row_refs(result, 2) == ["bot"]

    def test_join_vertical_different_widths_with_refs(self):
        """Narrower blocks get None-padded refs."""
        a = text_block(["ab"], ref="narrow")
        b = text_block(["cdef"], ref="wide")
        result = join_vertical(a, b)
        assert result.width == 4
        assert result._refs is not None
        # Row 0: narrow + right padding
        assert _row_refs(result, 0) == ["narrow", "narrow", None, None]
        assert _row_refs(result, 1) == ["wide", "wide", "wide", "wide"]

    def test_join_vertical_align_end_with_refs(self):
        """END alignment right-aligns narrower blocks, refs padded left."""
        a = text_block(["ab"], ref="r")
        b = text_block(["cdef"], ref="w")
        result = join_vertical(a, b, align=Align.END)
        assert result.width == 4
        # "ab" right-aligned: offset = 4 - 2 = 2
        assert row_text(result, 0) == "  ab"
        assert _row_refs(result, 0) == [None, None, "r", "r"]

    def test_join_vertical_align_center_with_refs(self):
        """CENTER alignment centers narrower blocks, refs padded."""
        a = text_block(["ab"], ref="c")
        b = text_block(["cdef"], ref="w")
        result = join_vertical(a, b, align=Align.CENTER)
        # offset = (4-2)//2 = 1
        assert row_text(result, 0) == " ab "
        assert _row_refs(result, 0) == [None, "c", "c", None]


# ---------------------------------------------------------------------------
# join_responsive edge cases
# ---------------------------------------------------------------------------


class TestJoinResponsiveExtended:
    def test_single_block_wider_than_available(self):
        """Single block wider than available still returns it (no truncation)."""
        a = text_block(["abcdef"])
        result = join_responsive(a, available_width=3)
        assert result.width == 6
        assert result.height == 1

    def test_three_blocks_fit(self):
        """Three blocks fitting horizontally."""
        a = text_block(["a"])
        b = text_block(["b"])
        c = text_block(["c"])
        result = join_responsive(a, b, c, available_width=5, gap=1)
        # 1+1+1+1+1 = 5, fits
        assert result.height == 1
        assert row_text(result, 0) == "a b c"

    def test_three_blocks_overflow(self):
        """Three blocks overflowing go vertical."""
        a = text_block(["aa"])
        b = text_block(["bb"])
        c = text_block(["cc"])
        result = join_responsive(a, b, c, available_width=5, gap=1)
        # 2+1+2+1+2 = 8 > 5, goes vertical
        # 3 blocks with gap=1 between: 1 + 1(gap) + 1 + 1(gap) + 1 = 5
        assert result.height == 5


# ---------------------------------------------------------------------------
# border() title edge cases
# ---------------------------------------------------------------------------


class TestBorderTitle:
    def test_border_with_title(self):
        """border() renders title in top row."""
        b = text_block(["abcdefgh"])
        result = border(b, title="Hi")
        top = row_text(result, 0)
        assert "Hi" in top

    def test_border_title_too_wide_skipped(self):
        """border() skips title if block too narrow."""
        b = text_block(["ab"])
        # Title "Hello" needs width + 3 = 8, block width is only 2
        result = border(b, title="Hello")
        top = row_text(result, 0)
        # Title should not appear
        assert "Hello" not in top

    def test_border_custom_chars(self):
        """border() uses custom chars."""
        b = text_block(["ab"])
        result = border(b, chars=HEAVY)
        assert result.width == 4
        assert result.height == 3

    def test_border_title_with_combining_char(self):
        """Zero-width combining chars in title are skipped (line 206)."""
        # U+0301 is a combining acute accent (zero-width).
        # Title "a\u0301b" has display_width 2 ("a" + combining + "b").
        # Block must be wide enough: need title_width(2) + 3 = 5.
        b = text_block(["abcde"])
        result = border(b, title="a\u0301b")
        top = row_text(result, 0)
        # The combining char is skipped, so "a" and "b" appear but not the accent.
        assert "a" in top
        assert "b" in top

    def test_border_title_exact_fit(self):
        """Title that exactly fits the available space."""
        # block.width=6, title "abc" (display_width=3), guard: 6 >= 3+3=6. Yes.
        # Painting: pos=2, space->3, a->4, b->5, c->6. Trailing space: 6<=6->yes.
        b = text_block(["abcdef"])
        result = border(b, title="abc")
        top = row_text(result, 0)
        assert "a" in top
        assert "b" in top
        assert "c" in top


# ---------------------------------------------------------------------------
# Alignment helpers (exercised via join functions)
# ---------------------------------------------------------------------------


class TestAlignment:
    def test_valign_center_via_join_horizontal(self):
        """CENTER vertical alignment offsets shorter blocks."""
        a = text_block(["x"])
        b = text_block(["1", "2", "3", "4", "5"])
        result = join_horizontal(a, b, align=Align.CENTER)
        assert result.height == 5
        # 'x' offset = (5-1)//2 = 2
        assert row_text(result, 2) == "x3"

    def test_valign_end_via_join_horizontal(self):
        """END vertical alignment pushes shorter block to bottom."""
        a = text_block(["x"])
        b = text_block(["1", "2", "3"])
        result = join_horizontal(a, b, align=Align.END)
        assert result.height == 3
        # 'x' at row 2 (offset = 3-1 = 2)
        assert row_text(result, 0) == " 1"
        assert row_text(result, 1) == " 2"
        assert row_text(result, 2) == "x3"

    def test_halign_center_via_join_vertical(self):
        """CENTER horizontal alignment centers narrower blocks."""
        a = text_block(["ab"])
        b = text_block(["123456"])
        result = join_vertical(a, b, align=Align.CENTER)
        assert result.width == 6
        # 'ab' offset = (6-2)//2 = 2
        assert row_text(result, 0) == "  ab  "

    def test_halign_end_via_join_vertical(self):
        """END horizontal alignment right-aligns blocks."""
        a = text_block(["ab"])
        b = text_block(["cdef"])
        result = join_vertical(a, b, align=Align.END)
        assert result.width == 4
        # 'ab' offset = 4-2 = 2
        assert row_text(result, 0) == "  ab"
        assert row_text(result, 1) == "cdef"
