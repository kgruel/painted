"""Tests for big text rendering.

FILLED is the 8×8 IBM bitmap font packed at a density (size=1 → HALF, 4 cells
tall; size=2 → FULL, 8 cells tall). OUTLINE is a separate box-drawing model with
its own 3-row / 5-row sizes. The two formats do NOT share a height.
"""

from painted import Style
from painted.views import BIG_GLYPHS, BigTextFormat, render_big
from painted.views.big_text import (
    _FULL_CHARS,
    _HALF_CHARS,
    _QUAD_CHARS,
    _Density,
    _glyph_bits,
    _pack,
)


class TestRenderBigFilled:
    """FILLED: 8×8 font packed at HALF (size=1) — 4 cells tall, glyphs 8 wide."""

    def test_single_char(self):
        """Single char packs to an 8×4 cell block at the default density."""
        block = render_big("a")
        assert block.height == 4
        assert block.width == 8

    def test_two_chars_with_gap(self):
        """Two glyphs: 8 + 1 (gap) + 8 = 17 wide."""
        block = render_big("ab")
        assert block.height == 4
        assert block.width == 17

    def test_word_width(self):
        """Width formula at size=1: n*8 + (n-1)*1 = n*9 - 1."""
        block = render_big("hello")
        assert block.width == 5 * 9 - 1  # 44
        assert block.height == 4

    def test_empty_string(self):
        """Empty string returns a 0-width, 4-tall block."""
        block = render_big("")
        assert block.width == 0
        assert block.height == 4

    def test_empty_string_size_2(self):
        """Empty string at size 2 returns a 0-width, 8-tall block."""
        block = render_big("", size=2)
        assert block.width == 0
        assert block.height == 8

    def test_case_folding(self):
        """Uppercase folds to lowercase — same glyph, same cells."""
        upper = render_big("ABC")
        lower = render_big("abc")
        assert upper.width == lower.width
        assert upper.height == lower.height
        for row in range(upper.height):
            assert [c.char for c in upper.row(row)] == [c.char for c in lower.row(row)]

    def test_unknown_char_renders_fallback(self):
        """Unknown chars pack the box fallback glyph (same as packing '\\x00')."""
        block = render_big("§")  # section sign — not in the font
        fallback = _pack(_glyph_bits("\x00"), Style(), _Density.HALF)
        assert block.height == 4
        assert block.width == 8
        for row in range(4):
            got = [c.char for c in block.row(row)]
            want = [c.char for c in fallback.row(row)]
            assert got == want

    def test_digits(self):
        """Digits 0-9 all render. 10 chars: 10*8 + 9 = 89."""
        block = render_big("0123456789")
        assert block.width == 10 * 9 - 1
        assert block.height == 4

    def test_punctuation(self):
        """Common punctuation renders. 6 chars: 6*8 + 5 = 53."""
        block = render_big(".,!?-:")
        assert block.height == 4
        assert block.width == 6 * 9 - 1

    def test_space_is_blank(self):
        """Space renders as a blank 8-wide glyph."""
        # 'a' (0-7), gap (8), space (9-16), gap (17), 'b' (18-25)
        block = render_big("a b")
        for row in range(4):
            cells = list(block.row(row))
            for col in (9, 10, 11, 12, 13, 14, 15, 16):
                assert cells[col].char == " "

    def test_whitespace_normalization(self):
        """Tabs and newlines collapse to spaces."""
        assert render_big("a\tb").width == render_big("a b").width

    def test_style_applied(self):
        """Style propagates to every cell."""
        style = Style(fg=(255, 0, 0), bold=True)
        block = render_big("x", style)
        for row in range(block.height):
            for cell in block.row(row):
                assert cell.style == style


class TestSizeIsDensity:
    """size selects a packing density over ONE 8×8 font."""

    def test_size_2_is_full_density(self):
        """size=2 packs at FULL: 8 cells tall, glyphs 8 wide."""
        block = render_big("a", size=2)
        assert block.height == 8
        assert block.width == 8

    def test_size_2_word_width(self):
        """size=2 width: n*8 + (n-1) = n*9 - 1."""
        block = render_big("hi", size=2)
        assert block.width == 2 * 9 - 1
        assert block.height == 8

    def test_size_2_style_applied(self):
        style = Style(fg=(0, 255, 0))
        block = render_big("x", style, size=2)
        for row in range(block.height):
            for cell in block.row(row):
                assert cell.style == style

    def test_denser_is_shorter(self):
        """HALF packing (size=1) is half the height of FULL (size=2)."""
        assert render_big("abc", size=1).height * 2 == render_big("abc", size=2).height


class TestPacker:
    """The density packer: a glyph bitmap → cells, one sub-grid per cell."""

    def test_quadrant_combos_round_trip(self):
        """Every one of the 16 quadrant patterns packs to its block char."""
        for (tl, tr, bl, br), char in _QUAD_CHARS.items():
            bits = [[tl, tr], [bl, br]]  # a 2×2 pixel grid
            block = _pack(bits, Style(), _Density.QUADRANT)
            assert block.width == 1 and block.height == 1
            assert block.row(0)[0].char == char

    def test_half_combos_round_trip(self):
        """Every (top, bottom) pattern packs to its half-block char."""
        for (top, bottom), char in _HALF_CHARS.items():
            bits = [[top], [bottom]]  # 1 col, 2 rows
            block = _pack(bits, Style(), _Density.HALF)
            assert block.width == 1 and block.height == 1
            assert block.row(0)[0].char == char

    def test_full_combos_round_trip(self):
        """FULL maps one pixel to one cell: space / █."""
        for (px,), char in _FULL_CHARS.items():
            block = _pack([[px]], Style(), _Density.FULL)
            assert block.row(0)[0].char == char

    def test_density_governs_dimensions(self):
        """An 8×8 grid → 8×8 (FULL), 8×4 (HALF), 4×4 (QUADRANT)."""
        bits = [[1] * 8 for _ in range(8)]
        assert (
            _pack(bits, Style(), _Density.FULL).width,
            _pack(bits, Style(), _Density.FULL).height,
        ) == (8, 8)
        assert (
            _pack(bits, Style(), _Density.HALF).width,
            _pack(bits, Style(), _Density.HALF).height,
        ) == (8, 4)
        assert (
            _pack(bits, Style(), _Density.QUADRANT).width,
            _pack(bits, Style(), _Density.QUADRANT).height,
        ) == (4, 4)

    def test_all_on_is_solid(self):
        """A fully-lit grid packs to solid █ at every density."""
        bits = [[1] * 8 for _ in range(8)]
        for density in (_Density.FULL, _Density.HALF, _Density.QUADRANT):
            block = _pack(bits, Style(), density)
            assert all(c.char == "█" for row in range(block.height) for c in block.row(row))

    def test_all_off_is_blank(self):
        """A fully-unlit grid packs to spaces at every density."""
        bits = [[0] * 8 for _ in range(8)]
        for density in (_Density.FULL, _Density.HALF, _Density.QUADRANT):
            block = _pack(bits, Style(), density)
            assert all(c.char == " " for row in range(block.height) for c in block.row(row))


class TestBigGlyphs:
    """The master 8×8 font (BIG_GLYPHS): 8 bytes per glyph + a fallback."""

    def test_glyphs_are_8_bytes(self):
        """Every glyph is exactly 8 bytes (one per pixel row)."""
        for char, glyph in BIG_GLYPHS.items():
            assert len(glyph) == 8, f"Glyph '{char}' has {len(glyph)} rows"
            assert all(0 <= b <= 0xFF for b in glyph), f"Glyph '{char}' has a non-byte row"

    def test_fallback_exists(self):
        assert "\x00" in BIG_GLYPHS

    def test_alphabet_coverage(self):
        for char in "abcdefghijklmnopqrstuvwxyz":
            assert char in BIG_GLYPHS, f"Missing glyph for '{char}'"

    def test_digit_coverage(self):
        for char in "0123456789":
            assert char in BIG_GLYPHS, f"Missing glyph for '{char}'"

    def test_common_punctuation_coverage(self):
        for char in " .,!?-:":
            assert char in BIG_GLYPHS, f"Missing glyph for '{char}'"


class TestBigTextFormat:
    """FILLED vs OUTLINE — different models, different natural heights."""

    def test_filled_is_default(self):
        filled = render_big("a")
        explicit = render_big("a", format=BigTextFormat.FILLED)
        for row in range(filled.height):
            assert [c.char for c in filled.row(row)] == [c.char for c in explicit.row(row)]

    def test_outline_size_1_is_three_rows(self):
        """OUTLINE keeps its own 3-row size — it is unchanged by the FILLED work."""
        block = render_big("a", format=BigTextFormat.OUTLINE)
        assert block.height == 3
        assert block.width == 3

    def test_outline_size_2_is_five_rows(self):
        block = render_big("ab", size=2, format=BigTextFormat.OUTLINE)
        assert block.height == 5
        assert block.width == 11  # 2*5 + 1

    def test_filled_and_outline_have_different_heights(self):
        """The two formats are different lenses, not two packings of one grid."""
        filled = render_big("o")
        outline = render_big("o", format=BigTextFormat.OUTLINE)
        assert filled.height != outline.height  # 4 vs 3

    def test_format_enum_values(self):
        assert BigTextFormat.FILLED.value == "filled"
        assert BigTextFormat.OUTLINE.value == "outline"

    def test_outline_uses_box_drawing(self):
        outline = render_big("o", format=BigTextFormat.OUTLINE)
        chars = {c.char for row in range(3) for c in outline.row(row)}
        assert chars & {"┌", "┐", "└", "┘", "│", "─"}, f"Expected box-drawing, got {chars}"
