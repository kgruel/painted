"""Tests for flame_lens — proportional hierarchical visualization."""

from painted.views import flame_lens
from tests.helpers import block_to_text


class TestFlameLensZoom:
    """Tests for flame_lens at each zoom level."""

    def test_zoom_0_shows_total(self):
        """At zoom 0, flame shows root label + total value."""
        data = {"render": 45, "diff": 30, "flush": 25}
        block = flame_lens(data, 0, 40)
        text = block_to_text(block)
        assert "100" in text  # total of 45+30+25

    def test_zoom_1_shows_single_row(self):
        """At zoom 1, flame shows top-level segments in one row."""
        data = {"render": 45, "diff": 30, "flush": 25}
        block = flame_lens(data, 1, 60)
        text = block_to_text(block)
        assert "render" in text
        assert "diff" in text
        assert "flush" in text
        assert block.height == 1

    def test_zoom_2_expands_children(self):
        """At zoom 2+, flame expands child segments into additional rows."""
        data = {"main": {"render": 45, "diff": 30, "flush": 25}}
        block = flame_lens(data, 2, 60)
        text = block_to_text(block)
        assert "main" in text
        assert "render" in text
        assert block.height >= 2


class TestFlameLensProportions:
    """Tests for proportional width allocation."""

    def test_segments_fill_width(self):
        """All segments together fill the available width."""
        data = {"a": 50, "b": 50}
        block = flame_lens(data, 1, 40)
        assert block.width == 40

    def test_larger_segment_gets_more_width(self):
        """Segment with larger value gets proportionally more characters."""
        data = {"big": 90, "small": 10}
        block = flame_lens(data, 1, 40)
        row = block.row(0)
        row_text = "".join(c.char for c in row)
        assert row_text.index("big") < row_text.index("small")

    def test_single_segment_fills_width(self):
        """A single segment fills the entire width."""
        data = {"only": 100}
        block = flame_lens(data, 1, 30)
        assert block.width == 30


class TestFlameLensEdgeCases:
    """Tests for edge cases."""

    def test_empty_data(self):
        """Empty dict produces valid output."""
        block = flame_lens({}, 1, 40)
        text = block_to_text(block)
        assert "no data" in text.lower() or block.height >= 1

    def test_zero_width_returns_empty(self):
        """Zero width returns empty block."""
        block = flame_lens({"a": 1}, 1, 0)
        assert block.width == 0

    def test_nested_three_levels(self):
        """Three-level nesting at high zoom."""
        data = {"top": {"mid": {"leaf": 100}}}
        block = flame_lens(data, 3, 60)
        text = block_to_text(block)
        assert "top" in text
        assert "mid" in text
        assert "leaf" in text

    def test_zero_values_handled(self):
        """Zero-valued segments don't cause division errors."""
        data = {"active": 100, "idle": 0}
        block = flame_lens(data, 1, 40)
        text = block_to_text(block)
        assert "active" in text

    def test_width_respected(self):
        """Output block respects width constraint."""
        data = {"a": 30, "b": 70}
        block = flame_lens(data, 1, 50)
        assert block.width == 50

    def test_more_segments_than_columns(self):
        """When segments outnumber columns, output still fits requested width."""
        data = {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1}
        block = flame_lens(data, 1, 3)
        assert block.width == 3


class TestFlameLensPalette:
    """flame_lens colors segments from the ambient palette's `series` ramp."""

    _DATA = {"main": {"render": 45, "diff": 30, "flush": 25}}

    @staticmethod
    def _cells(block):
        return [(c.char, c.style) for y in range(block.height) for c in block.row(y)]

    def test_default_flame_matches_legacy_cycle(self):
        """DEFAULT flame is byte-identical to the pre-`series` warm cycle.

        Parity is by construction, hash-seed independent: DEFAULT_PALETTE.series
        carries the exact (red, yellow, green, cyan) Styles the old
        `_flame_palette_colors()` derived from roles, and flame now applies
        `series[idx].merge(Style(reverse=True))` — the same Style the old
        `Style(fg=color, reverse=True)` produced. Same tuple + same index fn =>
        identical output regardless of PYTHONHASHSEED.
        """
        ambient = flame_lens(self._DATA, 2, 60)
        legacy = flame_lens(self._DATA, 2, 60, colors=("red", "yellow", "green", "cyan"))
        assert self._cells(ambient) == self._cells(legacy)

    def test_mono_flame_uses_no_color(self):
        """Honest monochrome: under MONO_PALETTE, flame segments carry no fg."""
        from painted.views import MONO_PALETTE, use_palette

        with use_palette(MONO_PALETTE):
            block = flame_lens(self._DATA, 2, 60)
        fgs = {c.style.fg for y in range(block.height) for c in block.row(y)}
        assert fgs == {None}, f"MONO flame leaked color: {fgs}"

    def test_painted_flame_uses_vivid_hex(self):
        """PAINTED_PALETTE routes vivid truecolor hexes into flame segments."""
        from painted.views import PAINTED_PALETTE, use_palette

        with use_palette(PAINTED_PALETTE):
            block = flame_lens(self._DATA, 2, 60)
        hexes = {
            c.style.fg
            for y in range(block.height)
            for c in block.row(y)
            if isinstance(c.style.fg, str) and c.style.fg.startswith("#")
        }
        assert hexes, "PAINTED flame produced no hex colors"
        assert hexes <= {s.fg for s in PAINTED_PALETTE.series}

    def test_nord_flame_uses_nord_hues(self):
        """NORD flame routes the Nord 256-color indices (ints) into segments.

        Guards the fix: the pre-`series` path stringified role fg, so "174"
        rendered as no color and NORD flame was effectively colorless. With
        int-valued `series`, segments carry real Nord hues again.
        """
        from painted.views import NORD_PALETTE, use_palette

        with use_palette(NORD_PALETTE):
            block = flame_lens(self._DATA, 2, 60)
        fgs = {
            c.style.fg for y in range(block.height) for c in block.row(y) if c.style.fg is not None
        }
        assert fgs, "NORD flame produced no colored segments"
        assert fgs <= {174, 179, 108, 110}
