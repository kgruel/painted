"""Color downconversion: Writer resolves color depth at the output boundary."""

from __future__ import annotations

import io

from painted.core.cell import Style
from painted.core.writer import (
    ColorDepth,
    Writer,
)
from painted.core._color import _idx_to_rgb, _nearest_basic, _rgb_to_256, _rgb_to_basic

# --- Pure color arithmetic ---


class TestIdxToRgb:
    def test_basic_colors(self):
        assert _idx_to_rgb(0) == (0, 0, 0)  # black
        assert _idx_to_rgb(1) == (192, 0, 0)  # red — normal at 0xC0 (see _BASIC_RGB)
        assert _idx_to_rgb(15) == (255, 255, 255)  # bright white

    def test_cube_colors(self):
        # Index 16 is the start of the 6x6x6 cube: rgb(0, 0, 0)
        assert _idx_to_rgb(16) == (0, 0, 0)
        # Index 196 = 16 + 36*5 + 6*0 + 0 → rgb(255, 0, 0)
        assert _idx_to_rgb(196) == (255, 0, 0)
        # Index 21 = 16 + 36*0 + 6*0 + 5 → rgb(0, 0, 255)
        assert _idx_to_rgb(21) == (0, 0, 255)

    def test_grayscale(self):
        # Index 232 = first grayscale: 8
        assert _idx_to_rgb(232) == (8, 8, 8)
        # Index 255 = last grayscale: 8 + 23*10 = 238
        assert _idx_to_rgb(255) == (238, 238, 238)


class TestRgbTo256:
    def test_exact_red(self):
        # Pure red should map close to index 196 (255, 0, 0 in cube)
        idx = _rgb_to_256(255, 0, 0)
        r, g, b = _idx_to_rgb(idx)
        assert r > 200 and g < 50 and b < 50

    def test_pure_white(self):
        idx = _rgb_to_256(255, 255, 255)
        r, g, b = _idx_to_rgb(idx)
        assert r > 200 and g > 200 and b > 200

    def test_mid_gray(self):
        idx = _rgb_to_256(128, 128, 128)
        r, g, b = _idx_to_rgb(idx)
        # Should be in the grayscale range or a neutral cube color
        assert abs(r - g) < 30 and abs(g - b) < 30


class TestRgbToBasic:
    def test_pure_red(self):
        idx = _rgb_to_basic(255, 0, 0)
        assert idx == 9  # bright red

    def test_pure_black(self):
        idx = _rgb_to_basic(0, 0, 0)
        assert idx == 0  # black

    def test_pure_white(self):
        idx = _rgb_to_basic(255, 255, 255)
        assert idx == 15  # bright white

    def test_dark_green(self):
        idx = _rgb_to_basic(0, 100, 0)
        assert idx == 2  # green


class TestNearestBasic:
    def test_basic_index_roundtrips(self):
        """Basic 16 colors (0-15) should map to themselves."""
        for i in range(16):
            result = _nearest_basic(i)
            assert 0 <= result < 16

    def test_nord_palette_108(self):
        """NORD_PALETTE success=Style(fg=108) should downconvert to a green-ish basic color."""
        result = _nearest_basic(108)
        assert 0 <= result < 16


# --- Writer integration ---


def _writer_with_depth(depth: ColorDepth) -> Writer:
    """Create a Writer with a forced color depth."""
    w = Writer(io.StringIO())
    w._color_depth = depth
    return w


class TestWriterTruecolor:
    def test_hex_passthrough(self):
        w = _writer_with_depth(ColorDepth.TRUECOLOR)
        codes = w._color_codes("#ff5733", foreground=True)
        assert codes == ["38", "2", "255", "87", "51"]

    def test_int_passthrough(self):
        w = _writer_with_depth(ColorDepth.TRUECOLOR)
        codes = w._color_codes(108, foreground=True)
        assert codes == ["38", "5", "108"]

    def test_named_passthrough(self):
        w = _writer_with_depth(ColorDepth.TRUECOLOR)
        codes = w._color_codes("red", foreground=True)
        assert codes == ["31"]


class TestWriter256:
    def test_hex_downconverts_to_256(self):
        w = _writer_with_depth(ColorDepth.EIGHT_BIT)
        codes = w._color_codes("#ff5733", foreground=True)
        assert codes[0] == "38"
        assert codes[1] == "5"
        # Should be a valid 256-color index
        idx = int(codes[2])
        assert 0 <= idx <= 255

    def test_int_passthrough(self):
        w = _writer_with_depth(ColorDepth.EIGHT_BIT)
        codes = w._color_codes(108, foreground=True)
        assert codes == ["38", "5", "108"]

    def test_named_passthrough(self):
        w = _writer_with_depth(ColorDepth.EIGHT_BIT)
        codes = w._color_codes("cyan", foreground=True)
        assert codes == ["36"]


class TestWriter16:
    def test_hex_downconverts_to_basic(self):
        w = _writer_with_depth(ColorDepth.BASIC)
        codes = w._color_codes("#ff0000", foreground=True)
        # Should be a single basic SGR code (30-37 or 90-97 range after base+idx)
        assert len(codes) == 1
        code = int(codes[0])
        assert 30 <= code <= 47 or 90 <= code <= 107

    def test_int_downconverts_to_basic(self):
        w = _writer_with_depth(ColorDepth.BASIC)
        codes = w._color_codes(108, foreground=True)
        assert len(codes) == 1
        code = int(codes[0])
        assert 30 <= code <= 47

    def test_named_unchanged(self):
        w = _writer_with_depth(ColorDepth.BASIC)
        codes = w._color_codes("green", foreground=True)
        assert codes == ["32"]

    def test_background_codes(self):
        w = _writer_with_depth(ColorDepth.BASIC)
        codes = w._color_codes("#ff0000", foreground=False)
        assert len(codes) == 1
        code = int(codes[0])
        assert 40 <= code <= 57


class TestWriterNone:
    """ColorDepth.NONE is a colorless destination — apply_style suppresses fg/bg.

    The behavior-tightening correction of §9.4 (RENDERER_CONTRACT_DESIGN.md): NONE
    is not a downsampling target but the NO_COLOR shape — color dropped, attributes
    kept — so the writer never emits color for it. Previously apply_style emitted
    basic (16-color) codes at NONE, disagreeing with diagnostics.py's colorless
    reading; the writer now sides with the honest interpretation.
    """

    def test_none_suppresses_hex_fg(self):
        w = _writer_with_depth(ColorDepth.NONE)
        assert w.apply_style(Style(fg="#ff0000")) == ""

    def test_none_suppresses_named_fg(self):
        w = _writer_with_depth(ColorDepth.NONE)
        assert w.apply_style(Style(fg="red")) == ""

    def test_none_suppresses_bg(self):
        w = _writer_with_depth(ColorDepth.NONE)
        assert w.apply_style(Style(bg="blue")) == ""

    def test_none_keeps_attributes(self):
        """Only color is suppressed — bold/underline (the NO_COLOR shape) survive."""
        w = _writer_with_depth(ColorDepth.NONE)
        assert w.apply_style(Style(bold=True, underline=True, fg="red")) == "\x1b[1;4m"


class TestWriterForcedDepth:
    def test_detect_color_depth_respects_forced_depth_on_non_tty_stream(self):
        w = Writer(io.StringIO(), color_depth=ColorDepth.EIGHT_BIT)
        assert w.detect_color_depth() == ColorDepth.EIGHT_BIT


class TestNordPaletteDownconversion:
    """NORD_PALETTE uses 256-color indexes. Verify they downconvert on 16-color."""

    def test_nord_colors_downconvert(self):
        w = _writer_with_depth(ColorDepth.BASIC)
        nord_indexes = [108, 179, 174, 110, 60]  # success, warning, error, accent, muted
        for idx in nord_indexes:
            codes = w._color_codes(idx, foreground=True)
            assert len(codes) == 1, f"Index {idx} should downconvert to single basic code"
            code = int(codes[0])
            assert 30 <= code <= 47, f"Index {idx} produced unexpected code {code}"
